using Temporalio.Client;
using Temporalio.Worker;

namespace DejaVu;

public static class Program
{
    public static async Task Main(string[] args)
    {
        var temporalAddr = Environment.GetEnvironmentVariable("TEMPORAL_ADDRESS") ?? "localhost:7233";
        var taskQueue = Environment.GetEnvironmentVariable("TEMPORAL_TASK_QUEUE") is { Length: > 0 } tq ? tq : "dejavu-tacos";
        var backendUrl = Environment.GetEnvironmentVariable("DEJAVU_BACKEND_URL") ?? "http://localhost:8000";

        var client = await TemporalClient.ConnectAsync(new(temporalAddr));

        var backend = new BackendClient(backendUrl);
        var activities = new OrderActivities(backend);

        using var worker = new TemporalWorker(client, new TemporalWorkerOptions(taskQueue)
            .AddWorkflow<OrderWorkflow>()
            .AddAllActivities(activities));

        Console.WriteLine($"C# worker started, listening on task queue: {taskQueue}");
        Console.WriteLine($"Backend URL: {backendUrl}");
        Console.WriteLine($"Temporal address: {temporalAddr}");

        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
        await worker.ExecuteAsync(cts.Token);
    }
}
