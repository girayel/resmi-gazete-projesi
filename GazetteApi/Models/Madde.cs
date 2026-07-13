namespace GazetteApi.Models;

// legislative_section / executive_administrative_section / judicial_section /
// announcement_section tablolarinin dordu de ayni sutunlara sahip oldugu icin
// tek bir sinifla temsil ediyoruz. Hangi tablodan geldigini "Bolum" alani soyler.
public class Madde
{
    public int Id { get; set; }
    public int GazetteId { get; set; }
    public string Bolum { get; set; } = "";
    public string Title { get; set; } = "";
    public string Link { get; set; } = "";
    public string? ContentType { get; set; }

    // pdf_content (bytea) veritabanindan ham bayt olarak gelir; API'den
    // disariya cikarken UTF-8 metne cevirip burada tutuyoruz (Python'daki
    // convert_from(pdf_content, 'UTF8') ile ayni is).
    public string? Icerik { get; set; }
}
