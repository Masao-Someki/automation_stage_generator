import subprocess
from pathlib import Path
from typing import Any


def build_worker_command(
    cli_path: Path,
    provider_name: str,
    model_name: str,
    stage_script: Path,
    messages_in: Path,
    messages_out: Path,
) -> list[str]:
    return [
        "python",
        str(cli_path),
        "--provider",
        provider_name,
        "--model",
        model_name,
        "--run-stage-script",
        str(stage_script),
        "--messages-in",
        str(messages_in),
        "--messages-out",
        str(messages_out),
    ]


def _submit_local(cmd: list[str], cwd: Path) -> dict[str, Any]:
    process = subprocess.Popen(cmd, cwd=cwd)
    return {
        "executor_type": "local",
        "pid": process.pid,
        "process": process,
    }


def _submit_slurm(cmd: list[str], cwd: Path, slurm_config: dict[str, Any]) -> dict[str, Any]:
    # Use --parsable to capture only the job id.
    wrap_cmd = subprocess.list2cmdline(cmd)
    sbatch_cmd = ["sbatch", "--parsable"]

    partition = slurm_config.get("partition")
    if partition:
        sbatch_cmd.extend(["-p", str(partition)])

    cpus = slurm_config.get("cpus_per_task")
    if cpus:
        sbatch_cmd.extend(["-c", str(cpus)])

    memory = slurm_config.get("mem")
    if memory:
        sbatch_cmd.extend(["--mem", str(memory)])

    time_limit = slurm_config.get("time")
    if time_limit:
        sbatch_cmd.extend(["-t", str(time_limit)])

    sbatch_cmd.extend(["--wrap", wrap_cmd])

    completed = subprocess.run(
        sbatch_cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"sbatch failed: {detail}")

    output = (completed.stdout or "").strip()
    # --parsable can return "<jobid>" or "<jobid>;cluster"
    job_id = output.split(";")[0].strip()
    if not job_id:
        raise RuntimeError(f"sbatch returned empty job id: {output}")

    return {
        "executor_type": "slurm",
        "job_id": job_id,
        "sbatch_output": output,
    }


def submit_job(
    executor_type: str,
    cmd: list[str],
    cwd: Path,
    slurm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if executor_type == "local":
        return _submit_local(cmd, cwd)
    if executor_type == "slurm":
        return _submit_slurm(cmd, cwd, slurm_config or {})
    raise ValueError(f"Unsupported executor_type: {executor_type}")


def _poll_local(job: dict[str, Any]) -> dict[str, Any]:
    process = job["process"]
    return_code = process.poll()
    if return_code is None:
        return {"done": False, "status": "running"}
    if return_code == 0:
        return {"done": True, "status": "succeeded", "return_code": 0}
    return {"done": True, "status": "failed", "return_code": return_code}


def _poll_slurm(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job["job_id"])
    # Prefer sacct for reliable terminal states.
    completed = subprocess.run(
        ["sacct", "-j", job_id, "--format=State", "--noheader", "--parsable2"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"sacct failed for job {job_id}: {detail}")

    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    if not lines:
        return {"done": False, "status": "running"}

    # Use the first non-empty state as the job state.
    state = lines[0].split("|")[0].strip().upper()
    if state in {"PENDING", "RUNNING", "COMPLETING", "CONFIGURING"}:
        return {"done": False, "status": "running", "slurm_state": state}
    if state in {"COMPLETED"}:
        return {"done": True, "status": "succeeded", "slurm_state": state}
    return {"done": True, "status": "failed", "slurm_state": state}


def poll_job(job: dict[str, Any]) -> dict[str, Any]:
    executor_type = job.get("executor_type")
    if executor_type == "local":
        return _poll_local(job)
    if executor_type == "slurm":
        return _poll_slurm(job)
    raise ValueError(f"Unsupported executor_type for polling: {executor_type}")
