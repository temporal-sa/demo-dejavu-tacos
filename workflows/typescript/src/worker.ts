import { NativeConnection, Worker } from "@temporalio/worker";
import { createActivities } from "./activities";
import { BackendClient } from "./backend-client";

async function main() {
  const temporalAddr = process.env.TEMPORAL_ADDRESS || "localhost:7233";
  const taskQueue = process.env.TEMPORAL_TASK_QUEUE || "dejavu-tacos";
  const backendURL =
    process.env.DEJAVU_BACKEND_URL || "http://localhost:8000";

  const connection = await NativeConnection.connect({
    address: temporalAddr,
  });

  const backend = new BackendClient(backendURL);

  const worker = await Worker.create({
    connection,
    namespace: "default",
    taskQueue,
    workflowsPath: require.resolve("./workflows"),
    activities: createActivities(backend),
  });

  console.log(`TypeScript worker started, listening on task queue: ${taskQueue}`);
  console.log(`Backend URL: ${backendURL}`);
  console.log(`Temporal address: ${temporalAddr}`);

  await worker.run();
}

main().catch((err) => {
  console.error("Worker failed:", err);
  process.exit(1);
});
