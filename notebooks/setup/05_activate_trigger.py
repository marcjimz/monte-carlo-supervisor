# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # 05 — Activate Simulation Pipeline Trigger
# MAGIC
# MAGIC Unpauses the table-update trigger on the simulation pipeline job
# MAGIC so it fires whenever `simulation_runs` is updated.
# MAGIC
# MAGIC Runs as the final task in `data_pipeline` after the monitored
# MAGIC table has been created.

# COMMAND ----------

dbutils.widgets.text("simulation_job_id", "", "Simulation Pipeline Job ID")
simulation_job_id = dbutils.widgets.get("simulation_job_id")

print(f"Simulation Job ID: {simulation_job_id}")

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

job = w.jobs.get(int(simulation_job_id))
trigger = job.settings.trigger
print(f"Current trigger pause_status: {trigger.pause_status if trigger else 'no trigger'}")

if trigger and str(trigger.pause_status) != "PauseStatus.UNPAUSED":
    w.api_client.do(
        "POST",
        "/api/2.1/jobs/update",
        body={
            "job_id": int(simulation_job_id),
            "new_settings": {
                "trigger": {"pause_status": "UNPAUSED"},
            },
        },
    )
    print(f"Trigger unpaused for job {simulation_job_id}")
else:
    print("Trigger already unpaused — nothing to do")
