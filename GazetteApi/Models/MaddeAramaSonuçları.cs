namespace GazetteApi.Models;

// /api/madde-arama sonuclarinda hangi gazete gunune ait oldugunu da
// gostermek icin Madde ile ayni alanlara ek olarak Date tasir.
public class MaddeAramaSonucu
{
    public int Id { get; set; }
    public int GazetteId { get; set; }
    public DateOnly Date { get; set; }
    public string Bolum { get; set; } = "";
    public string Title { get; set; } = "";
    public string Link { get; set; } = "";
    public string? ContentType { get; set; }
    public string? Icerik { get; set; }
}

public class MaddeAramaSonucuPage
{
    public List<MaddeAramaSonucu> Items { get; set; } = new();
    public int TotalCount { get; set; }
    public int Page { get; set; }
    public int PageSize { get; set; }
}