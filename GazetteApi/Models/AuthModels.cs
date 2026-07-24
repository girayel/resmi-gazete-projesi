namespace GazetteApi.Models;

public record RegisterRequest(string Email, string Password);

public record LoginRequest(string Email, string Password);

public record AuthResponse(string Token, int UserId, string Email, string Role);

public record UserSummary(int Id, string Email, string Role, DateTimeOffset CreatedAt, bool IsActive);
public record ForgotPasswordRequest(string Email);

public record ResetPasswordRequest(string Token, string NewPassword);


public record UpdateUserRoleRequest(string Role);

public record UpdateUserStatusRequest(bool IsActive);
