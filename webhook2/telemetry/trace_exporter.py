from typing import Any
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

class WorkflowTraceExporter(AzureMonitorTraceExporter):
    """
    A custom trace exporter that extends AzureMonitorTraceExporter to modify the span to envelope conversion.
    This allows correlating the spans with workflow runs and jobs without needing to preserve the original spans in memory.
    """

    # Application Insights correlation docs:
    # - https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model-complete#context
    # - https://learn.microsoft.com/en-us/azure/azure-monitor/app/dotnet?tabs=net%2Cnet-1%2Cserver%2Cportal%2Ccsharp%2Cenqueue%2Capi-net#distributed-tracing

    # The goals for correlation are:
    # - all telemetry should have a unique id
    # - all telemetry for a workflow run (including jobs and child runs etc) should share the same operation id
    # - jobs should have the id of the workflow run as their operation parent id
    # - child workflow runs should have the id of the parent workflow run as their operation parent id

    # This translates to:
    #  - top-level workflows use the run_id and run_attempt as the id, operation id, and operation parent id
    #  - jobs use the job_id as the id, and the run_id and run_attempt as the operation id and operation parent id


    def _span_to_envelope(self, span):
        # NOTE: the current implementation only works for one level of nesting
        # To handle deeper nesting, we would need a way to look up the parent run's parent run etc

        envelope : Any = super()._span_to_envelope(span)
        properties = envelope.data.base_data.properties
        organization = properties.get("organization", None)
        repository = properties.get("repository", None)
        run_id = properties.get("run_id", None)
        run_attempt = properties.get("run_attempt", None)
        parent_run_id = properties.get("parent_run_id", None)
        parent_run_attempt = properties.get("parent_run_attempt", None)
        parent_job_name = properties.get("parent_job_name", None)
        if run_id and run_attempt:
            # we've got run or job related telemetry to process

            # set the operation id to a consistent value for all related telemetry
            if parent_run_id and parent_run_attempt:
                # use parent run for operation id to correlate spawned workflows
                operation_id = f"{organization}#{repository}#{parent_run_id}#{parent_run_attempt}"
                current_id = f"{organization}#{repository}#{run_id}#{run_attempt}"
            else:
                operation_id = f"{organization}#{repository}#{run_id}#{run_attempt}"
                current_id = operation_id
            envelope.tags["ai.operation.id"] = operation_id


            item_id = None
            parent_id = None
            job_name = properties.get("job_name", None)
            if job_name:
                # it's a job
                item_id = f"{current_id}#{job_name}"
                parent_id = current_id
                pass
            else:
                if parent_run_id and parent_run_attempt:
                    # it's a child run
                    item_id = current_id
                    parent_id = f"{operation_id}#{parent_job_name}"
                else:
                    # it's a top-level run
                    item_id = current_id
                    parent_id = None
                    pass

            envelope.tags["ai.operation.parentId"] = parent_id
            envelope.data.base_data.id = item_id

        print(
            f"## Span: {span.name}\t\tenvelope: OperationID: {envelope.tags.get('ai.operation.id')}\tID: {envelope.data.base_data.id}\tOperationParentId: {envelope.tags.get('ai.operation.parentId')}")
        return envelope

    def _span_events_to_envelopes(self, span):
        envelopes = super()._span_events_to_envelopes(span)
        # Add custom logic here if needed
        print(f"Custom envelopes for span events: {span.name}")
        return envelopes
