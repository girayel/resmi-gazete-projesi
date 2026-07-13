namespace GazetteApi.Models;

// /api/gazette-issues icin sayfalanmis (paged) sonuc.
public class GazetteIssuesPage
{
    public List<GazetteIssue> Items { get; set; } = new();
    public int TotalCount { get; set; }
    public int Page { get; set; }
    public int PageSize { get; set; }
}
