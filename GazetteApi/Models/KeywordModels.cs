namespace GazetteApi.Models;

public record KeywordSummary(int Id, string Keyword, DateTimeOffset CreatedAt);

public record CreateKeywordRequest(string Keyword);

public record UserKeywordSummary(int KeywordId, string Keyword, DateTimeOffset SelectedAt);

public record SelectKeywordRequest(int KeywordId);
