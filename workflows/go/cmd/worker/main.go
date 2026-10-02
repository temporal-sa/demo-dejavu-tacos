package main

import (
	"log"
	"os"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"

	"github.com/mikeacjones/dejavu-tacos-temporal-oms-demo/workflows/go/activities"
	wf "github.com/mikeacjones/dejavu-tacos-temporal-oms-demo/workflows/go/workflows"
)

func main() {
	temporalAddr := os.Getenv("TEMPORAL_ADDRESS")
	if temporalAddr == "" {
		temporalAddr = "localhost:7233"
	}

	backendURL := os.Getenv("DEJAVU_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://localhost:8000"
	}

	taskQueue := os.Getenv("TEMPORAL_TASK_QUEUE")
	if taskQueue == "" {
		taskQueue = wf.DefaultTaskQueue
	}

	c, err := client.Dial(client.Options{
		HostPort: temporalAddr,
	})
	if err != nil {
		log.Fatalln("Unable to create Temporal client:", err)
	}
	defer c.Close()

	w := worker.New(c, taskQueue, worker.Options{})

	// Register workflow — name must match what the Python backend starts
	w.RegisterWorkflowWithOptions(wf.OrderWorkflow, workflow.RegisterOptions{
		Name: "OrderWorkflow",
	})

	// Register activities with backend client injected
	acts := &activities.Activities{
		Backend: activities.NewBackendClient(backendURL),
	}
	w.RegisterActivity(acts)

	log.Printf("Go worker started, listening on task queue: %s", taskQueue)
	log.Printf("Backend URL: %s", backendURL)
	log.Printf("Temporal address: %s", temporalAddr)

	if err := w.Run(worker.InterruptCh()); err != nil {
		log.Fatalln("Unable to start worker:", err)
	}
}
