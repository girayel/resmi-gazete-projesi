using System.Net;
using System.Net.Mail;
using System.Security.Claims;
using System.Security.Cryptography;
using System.IdentityModel.Tokens.Jwt;
using System.Text;
using System.Threading.RateLimiting;
using GazetteApi.Models;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.IdentityModel.Tokens;
using Npgsql;

JwtSecurityTokenHandler.DefaultMapInboundClaims = false;

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

var jwtKey = builder.Configuration["Jwt:Key"]
    ?? throw new InvalidOperationException("Jwt:Key ayarlanmamis (dotnet user-secrets set ile eklenmeli).");
var jwtIssuer = builder.Configuration["Jwt:Issuer"] ?? "GazetteApi";
var jwtAudience = builder.Configuration["Jwt:Audience"] ?? "GazetteApiUsers";
var jwtExpireMinutes = builder.Configuration.GetValue<int?>("Jwt:ExpireMinutes") ?? 120;

var smtpHost = builder.Configuration["Smtp:Host"];
var smtpPort = builder.Configuration.GetValue<int?>("Smtp:Port") ?? 587;
var smtpUser = builder.Configuration["Smtp:User"];
var smtpPassword = builder.Configuration["Smtp:Password"];
var smtpFrom = builder.Configuration["Smtp:From"] ?? smtpUser;
var frontendUrl = builder.Configuration["Frontend:Url"] ?? "http://localhost:5173";

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidIssuer = jwtIssuer,
            ValidateAudience = true,
            ValidAudience = jwtAudience,
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtKey)),
            ValidateLifetime = true,
        };
    });
builder.Services.AddAuthorization();

builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;

    // Giris/kayit denemeleri icin: IP basina dakikada 5 istek. Brute-force
    // (sifre tahmin etmeye calisma) saldirilarini yavaslatmak icin.
    options.AddPolicy("AuthPolicy", httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: httpContext.Connection.RemoteIpAddress?.ToString() ?? "bilinmeyen",
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 5,
                Window = TimeSpan.FromMinutes(1),
                QueueLimit = 0,
            }));

    // Sifre sifirlama istegi icin daha siki bir sinir: IP basina 10 dakikada 3
    // istek. Bu endpoint gercek e-posta gonderdigi icin (Gmail limiti ve
    // kullanicinin spam'e bogulmasi riski) daha temkinli davraniyoruz.
    options.AddPolicy("ForgotPasswordPolicy", httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: httpContext.Connection.RemoteIpAddress?.ToString() ?? "bilinmeyen",
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 3,
                Window = TimeSpan.FromMinutes(10),
                QueueLimit = 0,
            }));
});

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseHttpsRedirection();
app.UseCors(ReactDevPolicy);
app.UseAuthentication();
app.UseAuthorization();
app.UseRateLimiter();

app.MapGet("/api/gazette-issues", async (int page = 1, int pageSize = 20, string? search = null) =>
{
    page = Math.Max(1, page);
    pageSize = Math.Clamp(pageSize, 1, 100);

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    var aramaVar = !string.IsNullOrWhiteSpace(search);
    var whereClause = aramaVar
        ? "WHERE CAST(date AS TEXT) ILIKE @arama OR CAST(issue_number AS TEXT) ILIKE @arama"
        : "";

    int toplamKayit;
    await using (var sayimCmd = new NpgsqlCommand($"SELECT COUNT(*) FROM gazette_issue {whereClause}", conn))
    {
        if (aramaVar)
        {
            sayimCmd.Parameters.AddWithValue("arama", $"%{search}%");
        }
        toplamKayit = Convert.ToInt32(await sayimCmd.ExecuteScalarAsync());
    }

    var sonuclar = new List<GazetteIssue>();
    await using (var cmd = new NpgsqlCommand(
        $"SELECT id, date, issue_number, url, pdf_url FROM gazette_issue {whereClause} ORDER BY date OFFSET @offset LIMIT @limit",
        conn))
    {
        if (aramaVar)
        {
            cmd.Parameters.AddWithValue("arama", $"%{search}%");
        }
        cmd.Parameters.AddWithValue("offset", (page - 1) * pageSize);
        cmd.Parameters.AddWithValue("limit", pageSize);

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
    }

    return Results.Ok(new GazetteIssuesPage
    {
        Items = sonuclar,
        TotalCount = toplamKayit,
        Page = page,
        PageSize = pageSize,
    });
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

app.MapGet("/api/madde-arama", async (string? q, int page = 1, int pageSize = 20) =>
{
    if (string.IsNullOrWhiteSpace(q))
    {
        return Results.Ok(new MaddeAramaSonucuPage { Page = page, PageSize = pageSize });
    }

    page = Math.Max(1, page);
    pageSize = Math.Clamp(pageSize, 1, 100);

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    var tablolar = new[]
    {
        ("legislative", "legislative_section"),
        ("executive", "executive_administrative_section"),
        ("judicial", "judicial_section"),
        ("announcement", "announcement_section"),
    };

    var birlesmisSorgu = string.Join(" UNION ALL ", tablolar.Select(t =>
        $"SELECT '{t.Item1}' AS bolum, m.id, m.gazette_id, gi.date, m.title, m.link, m.content_type, m.pdf_content " +
        $"FROM {t.Item2} m JOIN gazette_issue gi ON gi.id = m.gazette_id " +
        "WHERE m.title ILIKE @q OR (m.pdf_content IS NOT NULL AND convert_from(m.pdf_content, 'UTF8') ILIKE @q)"));

    int toplamKayit;
    await using (var sayimCmd = new NpgsqlCommand($"SELECT COUNT(*) FROM ({birlesmisSorgu}) t", conn))
    {
        sayimCmd.Parameters.AddWithValue("q", $"%{q}%");
        toplamKayit = Convert.ToInt32(await sayimCmd.ExecuteScalarAsync());
    }

    var sonuclar = new List<MaddeAramaSonucu>();
    await using (var cmd = new NpgsqlCommand(
        $"SELECT bolum, id, gazette_id, date, title, link, content_type, pdf_content FROM ({birlesmisSorgu}) t " +
        "ORDER BY date DESC OFFSET @offset LIMIT @limit", conn))
    {
        cmd.Parameters.AddWithValue("q", $"%{q}%");
        cmd.Parameters.AddWithValue("offset", (page - 1) * pageSize);
        cmd.Parameters.AddWithValue("limit", pageSize);

        await using var reader = await cmd.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            string? icerik = null;
            if (!reader.IsDBNull(7))
            {
                var baytlar = (byte[])reader.GetValue(7);
                icerik = Encoding.UTF8.GetString(baytlar);
            }

            sonuclar.Add(new MaddeAramaSonucu
            {
                Bolum = reader.GetString(0),
                Id = reader.GetInt32(1),
                GazetteId = reader.GetInt32(2),
                Date = DateOnly.FromDateTime(reader.GetDateTime(3)),
                Title = reader.GetString(4),
                Link = reader.GetString(5),
                ContentType = reader.IsDBNull(6) ? null : reader.GetString(6),
                Icerik = icerik,
            });
        }
    }

    return Results.Ok(new MaddeAramaSonucuPage
    {
        Items = sonuclar,
        TotalCount = toplamKayit,
        Page = page,
        PageSize = pageSize,
    });
})
.WithName("MaddeArama");

app.MapPost("/api/auth/register", async (RegisterRequest istek) =>
{
    if (string.IsNullOrWhiteSpace(istek.Email) || string.IsNullOrWhiteSpace(istek.Password))
    {
        return Results.BadRequest(new { hata = "Email ve sifre zorunludur." });
    }
    if (istek.Password.Length < 6)
    {
        return Results.BadRequest(new { hata = "Sifre en az 6 karakter olmalidir." });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using (var kontrolCmd = new NpgsqlCommand("SELECT 1 FROM users WHERE email = @email", conn))
    {
        kontrolCmd.Parameters.AddWithValue("email", istek.Email);
        if (await kontrolCmd.ExecuteScalarAsync() is not null)
        {
            return Results.Conflict(new { hata = "Bu email ile kayitli bir kullanici zaten var." });
        }
    }

    var sifreHash = BCrypt.Net.BCrypt.HashPassword(istek.Password);

    int userId;
    await using (var cmd = new NpgsqlCommand(
        "INSERT INTO users (email, password_hash, role) VALUES (@email, @hash, 'user') RETURNING id",
        conn))
    {
        cmd.Parameters.AddWithValue("email", istek.Email);
        cmd.Parameters.AddWithValue("hash", sifreHash);
        userId = (int)(await cmd.ExecuteScalarAsync())!;
    }

    var token = JwtTokenUret(userId, istek.Email, "user");
    return Results.Created($"/api/auth/register/{userId}", new AuthResponse(token, userId, istek.Email, "user"));
})
.WithName("Register")
.RequireRateLimiting("AuthPolicy");

app.MapPost("/api/auth/login", async (LoginRequest istek) =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    int userId;
    string sifreHash;
    string rol;
    bool aktifMi;
    await using (var cmd = new NpgsqlCommand(
        "SELECT id, password_hash, role, is_active FROM users WHERE email = @email", conn))
    {
        cmd.Parameters.AddWithValue("email", istek.Email);
        await using var reader = await cmd.ExecuteReaderAsync();
        if (!await reader.ReadAsync())
        {
            return Results.Unauthorized();
        }
        userId = reader.GetInt32(0);
        sifreHash = reader.GetString(1);
        rol = reader.GetString(2);
        aktifMi = reader.GetBoolean(3);
    }

    if (!BCrypt.Net.BCrypt.Verify(istek.Password, sifreHash))
    {
        return Results.Unauthorized();
    }

    if (!aktifMi)
    {
        return Results.Json(new { hata = "Hesabiniz pasif durumda. Yonetici ile iletisime gecin." }, statusCode: 403);
    }

    var token = JwtTokenUret(userId, istek.Email, rol);
    return Results.Ok(new AuthResponse(token, userId, istek.Email, rol));
})
.WithName("Login")
.RequireRateLimiting("AuthPolicy");

app.MapPost("/api/auth/forgot-password", async (ForgotPasswordRequest istek) =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    int? userId = null;
    await using (var cmd = new NpgsqlCommand("SELECT id FROM users WHERE email = @email", conn))
    {
        cmd.Parameters.AddWithValue("email", istek.Email);
        if (await cmd.ExecuteScalarAsync() is int id)
        {
            userId = id;
        }
    }

    // Kullanici bulunamasa bile ayni genel mesaji donuyoruz - "bu email kayitli mi
    // degil mi" bilgisini disariya sizdirmemek icin (email enumeration'i onlemek).
    if (userId is not null)
    {
        var token = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
            .Replace('+', '-').Replace('/', '_').TrimEnd('=');
        var sonKullanma = DateTimeOffset.UtcNow.AddHours(1);

        await using (var insertCmd = new NpgsqlCommand(
            "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (@userId, @token, @expiresAt)",
            conn))
        {
            insertCmd.Parameters.AddWithValue("userId", userId.Value);
            insertCmd.Parameters.AddWithValue("token", token);
            insertCmd.Parameters.AddWithValue("expiresAt", sonKullanma);
            await insertCmd.ExecuteNonQueryAsync();
        }

        var sifirlamaLinki = $"{frontendUrl}/?resetToken={token}";
        await EpostaGonder(
            istek.Email,
            "Resmi Gazete - Sifre Sifirlama",
            $"Sifreni sifirlamak icin asagidaki linke tikla:\n\n{sifirlamaLinki}\n\nBu link 1 saat gecerlidir. Bu istegi sen yapmadiysan bu maili yoksayabilirsin.");
    }

    return Results.Ok(new { mesaj = "Bu email kayitliysa, sifre sifirlama baglantisi gonderildi." });
})
.WithName("ForgotPassword")
.RequireRateLimiting("ForgotPasswordPolicy");

app.MapPost("/api/auth/reset-password", async (ResetPasswordRequest istek) =>
{
    if (string.IsNullOrWhiteSpace(istek.NewPassword) || istek.NewPassword.Length < 6)
    {
        return Results.BadRequest(new { hata = "Sifre en az 6 karakter olmalidir." });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    int userId;
    await using (var cmd = new NpgsqlCommand(
        "SELECT user_id FROM password_reset_tokens WHERE token = @token AND used_at IS NULL AND expires_at > now()",
        conn))
    {
        cmd.Parameters.AddWithValue("token", istek.Token);
        if (await cmd.ExecuteScalarAsync() is not int id)
        {
            return Results.BadRequest(new { hata = "Bu baglanti gecersiz ya da suresi dolmus." });
        }
        userId = id;
    }

    var yeniHash = BCrypt.Net.BCrypt.HashPassword(istek.NewPassword);
    await using (var updateCmd = new NpgsqlCommand("UPDATE users SET password_hash = @hash WHERE id = @userId", conn))
    {
        updateCmd.Parameters.AddWithValue("hash", yeniHash);
        updateCmd.Parameters.AddWithValue("userId", userId);
        await updateCmd.ExecuteNonQueryAsync();
    }

    await using (var kullanCmd = new NpgsqlCommand(
        "UPDATE password_reset_tokens SET used_at = now() WHERE token = @token", conn))
    {
        kullanCmd.Parameters.AddWithValue("token", istek.Token);
        await kullanCmd.ExecuteNonQueryAsync();
    }

    return Results.Ok(new { mesaj = "Sifreniz basariyla degistirildi." });
})
.WithName("ResetPassword")
.RequireRateLimiting("AuthPolicy");

app.MapGet("/api/auth/me", (ClaimsPrincipal kullanici) =>
{
    var id = kullanici.FindFirstValue(JwtRegisteredClaimNames.Sub);
    var email = kullanici.FindFirstValue(JwtRegisteredClaimNames.Email);
    var rol = kullanici.FindFirstValue(ClaimTypes.Role);
    return Results.Ok(new { id, email, rol });
})
.RequireAuthorization()
.WithName("Me");

app.MapGet("/api/admin/users", async () =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    var kullanicilar = new List<UserSummary>();
    await using var cmd = new NpgsqlCommand(
        "SELECT id, email, role, created_at, is_active FROM users ORDER BY id", conn);

    await using var reader = await cmd.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
        kullanicilar.Add(new UserSummary(
            reader.GetInt32(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetFieldValue<DateTimeOffset>(3),
            reader.GetBoolean(4)));
    }

    return Results.Ok(kullanicilar);
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminGetUsers");

app.MapGet("/api/keywords", async () =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    var kelimeler = new List<KeywordSummary>();
    await using var cmd = new NpgsqlCommand(
        "SELECT id, keyword, created_at FROM keywords ORDER BY keyword", conn);

    await using var reader = await cmd.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
        kelimeler.Add(new KeywordSummary(
            reader.GetInt32(0),
            reader.GetString(1),
            reader.GetFieldValue<DateTimeOffset>(2)));
    }

    return Results.Ok(kelimeler);
})
.RequireAuthorization()
.WithName("GetKeywords");

app.MapPost("/api/keywords", async (CreateKeywordRequest istek) =>
{
    var kelime = istek.Keyword?.Trim() ?? "";
    if (string.IsNullOrWhiteSpace(kelime))
    {
        return Results.BadRequest(new { hata = "Keyword bos olamaz." });
    }
    if (kelime.Length > 100)
    {
        return Results.BadRequest(new { hata = "Keyword en fazla 100 karakter olabilir." });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using (var kontrolCmd = new NpgsqlCommand("SELECT 1 FROM keywords WHERE keyword = @kelime", conn))
    {
        kontrolCmd.Parameters.AddWithValue("kelime", kelime);
        if (await kontrolCmd.ExecuteScalarAsync() is not null)
        {
            return Results.Conflict(new { hata = "Bu keyword zaten havuzda var." });
        }
    }

    int id;
    DateTimeOffset olusturulmaZamani;
    await using (var cmd = new NpgsqlCommand(
        "INSERT INTO keywords (keyword) VALUES (@kelime) RETURNING id, created_at", conn))
    {
        cmd.Parameters.AddWithValue("kelime", kelime);
        await using var reader = await cmd.ExecuteReaderAsync();
        await reader.ReadAsync();
        id = reader.GetInt32(0);
        olusturulmaZamani = reader.GetFieldValue<DateTimeOffset>(1);
    }

    return Results.Created($"/api/keywords/{id}", new KeywordSummary(id, kelime, olusturulmaZamani));
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("CreateKeyword");

app.MapDelete("/api/keywords/{id:int}", async (int id) =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using var cmd = new NpgsqlCommand("DELETE FROM keywords WHERE id = @id", conn);
    cmd.Parameters.AddWithValue("id", id);
    var silinenSatir = await cmd.ExecuteNonQueryAsync();

    return silinenSatir == 0 ? Results.NotFound(new { hata = "Bu id ile bir keyword bulunamadi." }) : Results.NoContent();
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("DeleteKeyword");

app.MapGet("/api/me/keywords", async (ClaimsPrincipal kullanici) =>
{
    var userId = int.Parse(kullanici.FindFirstValue(JwtRegisteredClaimNames.Sub)!);
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();
    return Results.Ok(await KullaniciKeywordleriniGetir(conn, userId));
})
.RequireAuthorization()
.WithName("GetMyKeywords");

app.MapPost("/api/me/keywords", async (ClaimsPrincipal kullanici, SelectKeywordRequest istek) =>
{
    var userId = int.Parse(kullanici.FindFirstValue(JwtRegisteredClaimNames.Sub)!);

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    var hata = await KeywordAtamaGecerliMi(conn, userId, istek.KeywordId);
    if (hata is not null)
    {
        return hata;
    }

    await KeywordAta(conn, userId, istek.KeywordId, addedByUserId: null);
    return Results.Created($"/api/me/keywords/{istek.KeywordId}", new { keywordId = istek.KeywordId });
})
.RequireAuthorization()
.WithName("AddMyKeyword");

app.MapDelete("/api/me/keywords/{keywordId:int}", async (ClaimsPrincipal kullanici, int keywordId) =>
{
    var userId = int.Parse(kullanici.FindFirstValue(JwtRegisteredClaimNames.Sub)!);

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using var cmd = new NpgsqlCommand(
        "DELETE FROM user_keywords WHERE user_id = @userId AND keyword_id = @keywordId", conn);
    cmd.Parameters.AddWithValue("userId", userId);
    cmd.Parameters.AddWithValue("keywordId", keywordId);
    var silinenSatir = await cmd.ExecuteNonQueryAsync();

    return silinenSatir == 0 ? Results.NotFound(new { hata = "Bu keyword senin secimlerinde yok." }) : Results.NoContent();
})
.RequireAuthorization()
.WithName("RemoveMyKeyword");

app.MapGet("/api/admin/users/{userId:int}/keywords", async (int userId) =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    if (!await KullaniciVarMi(conn, userId))
    {
        return Results.NotFound(new { hata = "Bu id ile bir kullanici bulunamadi." });
    }

    return Results.Ok(await KullaniciKeywordleriniGetir(conn, userId));
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminGetUserKeywords");

app.MapPost("/api/admin/users/{userId:int}/keywords", async (ClaimsPrincipal admin, int userId, SelectKeywordRequest istek) =>
{
    var adminId = int.Parse(admin.FindFirstValue(JwtRegisteredClaimNames.Sub)!);

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    if (!await KullaniciVarMi(conn, userId))
    {
        return Results.NotFound(new { hata = "Bu id ile bir kullanici bulunamadi." });
    }

    var hata = await KeywordAtamaGecerliMi(conn, userId, istek.KeywordId);
    if (hata is not null)
    {
        return hata;
    }

    await KeywordAta(conn, userId, istek.KeywordId, adminId);
    return Results.Created($"/api/admin/users/{userId}/keywords/{istek.KeywordId}", new { userId, keywordId = istek.KeywordId });
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminAddUserKeyword");

app.MapDelete("/api/admin/users/{userId:int}/keywords/{keywordId:int}", async (int userId, int keywordId) =>
{
    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using var cmd = new NpgsqlCommand(
        "DELETE FROM user_keywords WHERE user_id = @userId AND keyword_id = @keywordId", conn);
    cmd.Parameters.AddWithValue("userId", userId);
    cmd.Parameters.AddWithValue("keywordId", keywordId);
    var silinenSatir = await cmd.ExecuteNonQueryAsync();

    return silinenSatir == 0 ? Results.NotFound(new { hata = "Bu kullanicida bu keyword secili degil." }) : Results.NoContent();
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminRemoveUserKeyword");

app.MapPatch("/api/admin/users/{userId:int}/role", async (ClaimsPrincipal admin, int userId, UpdateUserRoleRequest istek) =>
{
    var adminId = int.Parse(admin.FindFirstValue(JwtRegisteredClaimNames.Sub)!);
    if (userId == adminId)
    {
        return Results.BadRequest(new { hata = "Kendi rolunu degistiremezsin." });
    }
    if (istek.Role != "admin" && istek.Role != "user")
    {
        return Results.BadRequest(new { hata = "Rol 'admin' ya da 'user' olmalidir." });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    if (!await KullaniciVarMi(conn, userId))
    {
        return Results.NotFound(new { hata = "Bu id ile bir kullanici bulunamadi." });
    }

    await using var cmd = new NpgsqlCommand("UPDATE users SET role = @role WHERE id = @userId", conn);
    cmd.Parameters.AddWithValue("role", istek.Role);
    cmd.Parameters.AddWithValue("userId", userId);
    await cmd.ExecuteNonQueryAsync();

    return Results.Ok(new { userId, role = istek.Role });
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminUpdateUserRole");

app.MapPatch("/api/admin/users/{userId:int}/status", async (ClaimsPrincipal admin, int userId, UpdateUserStatusRequest istek) =>
{
    var adminId = int.Parse(admin.FindFirstValue(JwtRegisteredClaimNames.Sub)!);
    if (userId == adminId)
    {
        return Results.BadRequest(new { hata = "Kendi hesabini pasif yapamazsin." });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    if (!await KullaniciVarMi(conn, userId))
    {
        return Results.NotFound(new { hata = "Bu id ile bir kullanici bulunamadi." });
    }

    await using var cmd = new NpgsqlCommand("UPDATE users SET is_active = @isActive WHERE id = @userId", conn);
    cmd.Parameters.AddWithValue("isActive", istek.IsActive);
    cmd.Parameters.AddWithValue("userId", userId);
    await cmd.ExecuteNonQueryAsync();

    return Results.Ok(new { userId, isActive = istek.IsActive });
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminUpdateUserStatus");

app.MapDelete("/api/admin/users/{userId:int}", async (ClaimsPrincipal admin, int userId) =>
{
    var adminId = int.Parse(admin.FindFirstValue(JwtRegisteredClaimNames.Sub)!);
    if (userId == adminId)
    {
        return Results.BadRequest(new { hata = "Kendi hesabini silemezsin." });
    }

    await using var conn = new NpgsqlConnection(connectionString);
    await conn.OpenAsync();

    await using var cmd = new NpgsqlCommand("DELETE FROM users WHERE id = @userId", conn);
    cmd.Parameters.AddWithValue("userId", userId);
    var silinenSatir = await cmd.ExecuteNonQueryAsync();

    return silinenSatir == 0 ? Results.NotFound(new { hata = "Bu id ile bir kullanici bulunamadi." }) : Results.NoContent();
})
.RequireAuthorization(policy => policy.RequireRole("admin"))
.WithName("AdminDeleteUser");


app.Run();

async Task<bool> KullaniciVarMi(NpgsqlConnection conn, int userId)
{
    await using var cmd = new NpgsqlCommand("SELECT 1 FROM users WHERE id = @userId", conn);
    cmd.Parameters.AddWithValue("userId", userId);
    return await cmd.ExecuteScalarAsync() is not null;
}

async Task<List<UserKeywordSummary>> KullaniciKeywordleriniGetir(NpgsqlConnection conn, int userId)
{
    var kelimeler = new List<UserKeywordSummary>();
    await using var cmd = new NpgsqlCommand(
        "SELECT k.id, k.keyword, uk.created_at " +
        "FROM user_keywords uk JOIN keywords k ON k.id = uk.keyword_id " +
        "WHERE uk.user_id = @userId ORDER BY k.keyword",
        conn);
    cmd.Parameters.AddWithValue("userId", userId);

    await using var reader = await cmd.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
        kelimeler.Add(new UserKeywordSummary(
            reader.GetInt32(0),
            reader.GetString(1),
            reader.GetFieldValue<DateTimeOffset>(2)));
    }
    return kelimeler;
}

async Task<IResult?> KeywordAtamaGecerliMi(NpgsqlConnection conn, int userId, int keywordId)
{
    await using (var keywordKontrolCmd = new NpgsqlCommand("SELECT 1 FROM keywords WHERE id = @keywordId", conn))
    {
        keywordKontrolCmd.Parameters.AddWithValue("keywordId", keywordId);
        if (await keywordKontrolCmd.ExecuteScalarAsync() is null)
        {
            return Results.NotFound(new { hata = "Bu id ile bir keyword bulunamadi." });
        }
    }

    await using (var secimKontrolCmd = new NpgsqlCommand(
        "SELECT 1 FROM user_keywords WHERE user_id = @userId AND keyword_id = @keywordId", conn))
    {
        secimKontrolCmd.Parameters.AddWithValue("userId", userId);
        secimKontrolCmd.Parameters.AddWithValue("keywordId", keywordId);
        if (await secimKontrolCmd.ExecuteScalarAsync() is not null)
        {
            return Results.Conflict(new { hata = "Bu keyword zaten secilmis." });
        }
    }

    return null;
}

async Task KeywordAta(NpgsqlConnection conn, int userId, int keywordId, int? addedByUserId)
{
    await using var cmd = new NpgsqlCommand(
        "INSERT INTO user_keywords (user_id, keyword_id, added_by_user_id) VALUES (@userId, @keywordId, @addedByUserId)",
        conn);
    cmd.Parameters.AddWithValue("userId", userId);
    cmd.Parameters.AddWithValue("keywordId", keywordId);
    cmd.Parameters.AddWithValue("addedByUserId", (object?)addedByUserId ?? DBNull.Value);
    await cmd.ExecuteNonQueryAsync();
}

string JwtTokenUret(int userId, string email, string role)
{
    var claims = new[]
    {
        new Claim(JwtRegisteredClaimNames.Sub, userId.ToString()),
        new Claim(JwtRegisteredClaimNames.Email, email),
        new Claim(ClaimTypes.Role, role),
    };

    var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtKey));
    var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

    var token = new JwtSecurityToken(
        issuer: jwtIssuer,
        audience: jwtAudience,
        claims: claims,
        expires: DateTime.UtcNow.AddMinutes(jwtExpireMinutes),
        signingCredentials: creds);

    return new JwtSecurityTokenHandler().WriteToken(token);
}

async Task EpostaGonder(string hedefEmail, string konu, string govde)
{
    if (string.IsNullOrEmpty(smtpHost))
    {
        Console.WriteLine($"[SIMULASYON] SMTP yapilandirilmamis, gercek eposta gonderilmedi -> {hedefEmail}: {konu}");
        return;
    }

    try
    {
        using var mesaj = new MailMessage(smtpFrom!, hedefEmail, konu, govde);
        using var client = new SmtpClient(smtpHost, smtpPort)
        {
            Credentials = new NetworkCredential(smtpUser, smtpPassword),
            EnableSsl = true,
        };
        await client.SendMailAsync(mesaj);
        Console.WriteLine($"[EPOSTA] Gonderildi -> {hedefEmail}: {konu}");
    }
    catch (Exception e)
    {
        Console.WriteLine($"[EPOSTA HATASI] {hedefEmail}: {e.Message}");
    }
}
