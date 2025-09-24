from typing import Any
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

class WorkflowTraceExporter(AzureMonitorTraceExporter):
    """
    A custom trace exporter that extends AzureMonitorTraceExporter to modify the span to envelope conversion.
    This allows correlating the spans with workflow runs and jobs without needing to preserve the original spans in memory.
    """

    def _span_to_envelope(self, span):
        envelope : Any = super()._span_to_envelope(span)
        properties = envelope.data.base_data.properties
        run_id = properties.get("run_id", None)
        run_attempt = properties.get("run_attempt", None)
        if run_id and run_attempt:
            run_key = f"{run_id}#{run_attempt}"
            # we've got a run or a job
            # set the operation id to the run key
            envelope.tags["ai.operation.id"] = run_key
            job_id = properties.get("job_id", None)
            if job_id:
                # Got a job
                # set the parent id to the run key
                envelope.tags["ai.operation.parentId"] = run_key
                print(f"RunId: {run_id}\tJob ID: {job_id}")
            else:
                # No job id, so this is a run
                # set the ID to the run key (so that it can be used as a parent for jobs)
                envelope.data.base_data.id = run_key
                print(f"RunId: {run_id}\tNo Job ID")

        print(
            f"## envelope: OperationID: {envelope.tags.get('ai.operation.id')}\tID: {envelope.data.base_data.id}\tOperationParentId: {envelope.tags.get('ai.operation.parentId')} - SpanName: {span.name}")
        return envelope

    def _span_events_to_envelopes(self, span):
        envelopes = super()._span_events_to_envelopes(span)
        # Add custom logic here if needed
        print(f"Custom envelopes for span events: {span.name}")
        return envelopes
