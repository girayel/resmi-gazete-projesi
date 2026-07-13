namespace GazetteApi.Models;

// gazette_issue tablosunun bir satirini temsil eder.
public class GazetteIssue
{
    public int Id { get; set; }
    public DateOnly Date { get; set; }
    public int? IssueNumber { get; set; }
    public string Url { get; set; } = "";
    public string? PdfUrl { get; set; }
}
