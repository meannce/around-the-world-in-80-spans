using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT")
    ?? "http://otel-collector:4317";
var serviceName = Environment.GetEnvironmentVariable("OTEL_SERVICE_NAME")
    ?? "dotnet-station";

builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(serviceName))
    .WithTracing(t => t
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddOtlpExporter(o => o.Endpoint = new Uri(otlpEndpoint)));

builder.Services.AddHttpClient();

var app = builder.Build();

app.MapPost("/journey", async (HttpRequest req, IHttpClientFactory factory) =>
{
    var journey = await req.ReadFromJsonAsync<Dictionary<string, object>>() ?? new();

    var stops = journey.TryGetValue("stops", out var s) && s is System.Text.Json.JsonElement el
        ? el.EnumerateArray().Select(x => x.GetString()!).ToList()
        : new List<string>();

    stops.Add("dotnet-station");
    journey["stops"] = stops;
    journey["hop"] = journey.TryGetValue("hop", out var h) && h is System.Text.Json.JsonElement he
        ? he.GetInt32() + 1 : 1;

    var nextStop = Environment.GetEnvironmentVariable("NEXT_STOP") ?? "http://elixir-station:4000/journey";

    try
    {
        var client = factory.CreateClient();
        // W3C trace context is propagated automatically by HttpClientInstrumentation
        foreach (var (key, value) in req.Headers)
        {
            if (key.StartsWith("traceparent") || key.StartsWith("tracestate"))
                client.DefaultRequestHeaders.TryAddWithoutValidation(key, value.ToString());
        }
        await client.PostAsJsonAsync(nextStop, journey);
    }
    catch (Exception e)
    {
        Console.Error.WriteLine($"forward error: {e.Message}");
    }

    return Results.Ok(new { status = "passed", service = "dotnet-station", stops });
});

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.Run($"http://0.0.0.0:5001");
