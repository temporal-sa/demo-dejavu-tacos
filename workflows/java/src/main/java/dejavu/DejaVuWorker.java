package dejavu;

import io.temporal.client.WorkflowClient;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.serviceclient.WorkflowServiceStubsOptions;
import io.temporal.worker.Worker;
import io.temporal.worker.WorkerFactory;

/**
 * Entry point for the Java Temporal worker.
 * Connects to Temporal, registers the OrderWorkflow and activities,
 * then starts polling TEMPORAL_TASK_QUEUE (default "dejavu-tacos").
 */
public class DejaVuWorker {

    private static final String DEFAULT_TASK_QUEUE = "dejavu-tacos";

    public static void main(String[] args) {
        String temporalAddress = System.getenv("TEMPORAL_ADDRESS");
        if (temporalAddress == null || temporalAddress.isEmpty()) {
            temporalAddress = "localhost:7233";
        }

        String taskQueue = System.getenv("TEMPORAL_TASK_QUEUE");
        if (taskQueue == null || taskQueue.isEmpty()) {
            taskQueue = DEFAULT_TASK_QUEUE;
        }

        String backendUrl = System.getenv("DEJAVU_BACKEND_URL");
        if (backendUrl == null || backendUrl.isEmpty()) {
            backendUrl = "http://localhost:8000";
        }

        WorkflowServiceStubs service = WorkflowServiceStubs.newServiceStubs(
                WorkflowServiceStubsOptions.newBuilder()
                        .setTarget(temporalAddress)
                        .build());

        WorkflowClient client = WorkflowClient.newInstance(service);
        WorkerFactory factory = WorkerFactory.newInstance(client);

        Worker worker = factory.newWorker(taskQueue);

        // Register workflow
        worker.registerWorkflowImplementationTypes(OrderWorkflowImpl.class);

        // Register activities with backend client injected
        BackendClient backend = new BackendClient(backendUrl);
        worker.registerActivitiesImplementations(new OrderActivitiesImpl(backend));

        System.out.printf("Java worker started, listening on task queue: %s%n", taskQueue);
        System.out.printf("Backend URL: %s%n", backendUrl);
        System.out.printf("Temporal address: %s%n", temporalAddress);

        factory.start();
    }
}
