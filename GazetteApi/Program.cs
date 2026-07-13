using System.Text;
using GazetteApi.Models;
using Npgsql;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenApi();

const string ReactDevPolicy = "ReactDevPolicy";
builder.Services.AddCors(options =>
{
    options.AddPolicy(ReactDevPolicy, policy =>
    {
        policy.WithOrigins("http://localhost:5173", "http://localhost:3000")
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

var connectionString = builder.Configuration.GetConnectionString("GazetteDb")
    ?? throw new InvalidOperationException("ConnectionStrings:GazetteDb ayarlanmamis (dotnet user-secrets set ile eklenmeli).");

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseHttpsRedirection();
app.UseCors(ReactDevPolicy);

app.MapGet("/api/gazette-issues", async () =>
{
    var sonuclar = new List<GazetteIssue>();

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using var cmd = new NpgsqlCommand(
        "SELECT id, date, issue_number, url, pdf_url FROM gazette_issue ORDER BY date", conn);
    await using var reader = await cmd.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
        sonuclar.Add(new GazetteIssue
        {
            Id = reader.GetInt32(0),
            Date = DateOnly.FromDateTime(reader.GetDateTime(1)),
            IssueNumber = reader.IsDBNull(2) ? null : reader.GetInt32(2),
            Url = reader.GetString(3),
            PdfUrl = reader.IsDBNull(4) ? null : reader.GetString(4),
        });
    }

    return Results.Ok(sonuclar);
})
.WithName("GetGazetteIssues");

app.MapGet("/api/gazette-issues/{tarih}", async (string tarih) =>
{
    if (!DateOnly.TryParse(tarih, out var gun))
    {
        return Results.BadRequest(new { hata = "Tarih formati gecersiz. Ornek: 2026-06-03" });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    int? gazetteId = null;
    await using (var cmd = new NpgsqlCommand("SELECT id FROM gazette_issue WHERE date = @tarih", conn))
    {
        cmd.Parameters.AddWithValue("tarih", gun.ToDateTime(TimeOnly.MinValue));
        var sonuc = await cmd.ExecuteScalarAsync();
        if (sonuc is int id)
        {
            gazetteId = id;
        }
    }

    if (gazetteId is null)
    {
        return Results.NotFound(new { hata = $"{tarih} tarihine ait bir gazete kaydi bulunamadi." });
    }

    var maddeler = new List<Madde>();

    var tablolar = new[]
    {
        ("legislative", "legislative_section"),
        ("executive", "executive_administrative_section"),
        ("judicial", "judicial_section"),
        ("announcement", "announcement_section"),
    };

    foreach (var (bolumAdi, tabloAdi) in tablolar)
    {
        await using var cmd = new NpgsqlCommand(
            $"SELECT id, gazette_id, title, link, content_type, pdf_content FROM {tabloAdi} WHERE gazette_id = @id",
            conn);
        cmd.Parameters.AddWithValue("id", gazetteId.Value);

        await using var reader = await cmd.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            string? icerik = null;
            if (!reader.IsDBNull(5))
            {
                var baytlar = (byte[])reader.GetValue(5);
                icerik = Encoding.UTF8.GetString(baytlar);
            }

            maddeler.Add(new Madde
            {
                Id = reader.GetInt32(0),
                GazetteId = reader.GetInt32(1),
                Bolum = bolumAdi,
                Title = reader.GetString(2),
                Link = reader.GetString(3),
                ContentType = reader.IsDBNull(4) ? null : reader.GetString(4),
                Icerik = icerik,
            });
        }
    }

    return Results.Ok(maddeler);
})
.WithName("GetMaddelerByTarih");

app.Run();
