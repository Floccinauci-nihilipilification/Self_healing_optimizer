"""
operator.py — Self-Healing Kubernetes Operator using Kopf.
Watches for chaos events, queries ML API, and auto-heals.
"""

import kopf
import kubernetes
import httpx
import asyncio

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
ML_API_URL = os.getenv("ML_API_URL", "http://ml-api-service.default.svc.cluster.local:8000")

# Global clients (Initialized in startup)
v1 = None
apps_v1 = None
httpx_client = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("self-healer")

# ---------------------------------------------------------------------------
# Kopf Startup: Initialize global clients once
# ---------------------------------------------------------------------------
@kopf.on.startup()
async def configure(settings: kopf.OperatorSettings, **kwargs):
    global v1, apps_v1, httpx_client
    try:
        kubernetes.config.load_incluster_config()
        logger.info("☸️ Using In-Cluster Config")
    except Exception:
        kubernetes.config.load_kube_config()
        logger.info("🏡 Using Local Kube Config")
    
    v1 = kubernetes.client.CoreV1Api()
    apps_v1 = kubernetes.client.AppsV1Api()
    httpx_client = httpx.AsyncClient()

@kopf.on.cleanup()
async def cleanup(**kwargs):
    global httpx_client
    if httpx_client:
        await httpx_client.aclose()
        logger.info("🧹 Shared HTTP client closed.")

# ---------------------------------------------------------------------------
# Helper: Query Prometheus for a pod's CPU usage
# ---------------------------------------------------------------------------
async def get_pod_metrics(pod_name: str, namespace: str) -> dict:
    if not httpx_client:
        return {"cpu_usage": 10.0, "mem_usage": 50.0, "latency_ms": 120.0}
    try:
        cpu_query = f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}",namespace="{namespace}"}}[2m])'
        mem_query = f'container_memory_usage_bytes{{pod="{pod_name}",namespace="{namespace}"}}'

        # Run queries in parallel for maximum speed
        cpu_task = httpx_client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": cpu_query}, timeout=3)
        mem_task = httpx_client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": mem_query}, timeout=3)
        
        cpu_resp, mem_resp = await asyncio.gather(cpu_task, mem_task)

        cpu_data = cpu_resp.json()["data"]["result"]
        mem_data = mem_resp.json()["data"]["result"]

        cpu_usage = float(cpu_data[0]["value"][1]) * 100 if cpu_data else 10.0
        mem_bytes = float(mem_data[0]["value"][1]) if mem_data else 100 * 1024 * 1024
        mem_usage = (mem_bytes / (512 * 1024 * 1024)) * 100

        return {"cpu_usage": round(cpu_usage, 2), "mem_usage": round(mem_usage, 2), "latency_ms": 120.0}
    except Exception as e:
        logger.warning("Metrics fetch failed: %s", e)
        return {"cpu_usage": 10.0, "mem_usage": 50.0, "latency_ms": 120.0}


# ---------------------------------------------------------------------------
# Helper: Call ML API for anomaly analysis
# ---------------------------------------------------------------------------
async def analyze_with_ml(metrics: dict) -> dict:
    if not httpx_client:
        return {"is_anomaly": False, "threat_score": 0.0, "recommended_action": "NO_ACTION"}
    try:
        resp = await httpx_client.post(f"{ML_API_URL}/api/v1/analyze", json=metrics, timeout=3)
        return resp.json()
    except Exception as e:
        logger.warning("ML API call failed: %s", e)
        return {"is_anomaly": False, "threat_score": 0.0, "recommended_action": "NO_ACTION"}


# ---------------------------------------------------------------------------
# Helper: Restart a pod
# ---------------------------------------------------------------------------
async def restart_pod(pod_name: str, namespace: str):
    if not v1:
        return
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        logger.info("✅ Restarted pod: %s", pod_name)
    except Exception as e:
        logger.error("Failed to restart pod %s: %s", pod_name, e)


# ---------------------------------------------------------------------------
# Helper: Scale a deployment
# ---------------------------------------------------------------------------
async def scale_deployment(deployment_name: str, namespace: str, replicas: int = 2):
    if not apps_v1:
        return
    try:
        apps_v1.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace=namespace,
            body={"spec": {"replicas": replicas}}
        )
        logger.info("✅ Scaled %s to %d replicas", deployment_name, replicas)
    except Exception as e:
        logger.error("Failed to scale %s: %s", deployment_name, e)


# ---------------------------------------------------------------------------
# Kopf Handler: Watch pod failures
# ---------------------------------------------------------------------------
@kopf.on.field("pods", field="status.phase")
async def pod_phase_changed(old, new, name, namespace, **kwargs):
    if namespace not in ["applications"]:
        return

    if new in ["Failed", "Unknown"]:
        logger.info("🚨 Pod %s in %s entered phase: %s", name, namespace, new)

        metrics = await get_pod_metrics(name, namespace)
        result = await analyze_with_ml(metrics)

        logger.info("🧠 ML Result: anomaly=%s score=%.3f action=%s",
                    result.get("is_anomaly"), result.get("threat_score"), result.get("recommended_action"))

        if result.get("is_anomaly"):
            action = result.get("recommended_action")
            if action == "RESTART_POD":
                await restart_pod(name, namespace)
            elif action == "SCALE_OUT_HPA":
                await scale_deployment(name.rsplit("-", 2)[0], namespace, replicas=3)
            else:
                await restart_pod(name, namespace)
        else:
            # SAFETY FALLBACK: Even if ML says no anomaly, a Failed pod needs a restart for safety
            logger.info("🛡️ Safety Fallback: Restarting Failed pod despite no ML anomaly verdict")
            await restart_pod(name, namespace)


# ---------------------------------------------------------------------------
# Kopf Handler: Watch for high restart counts (CrashLoopBackOff)
# ---------------------------------------------------------------------------
@kopf.on.field("pods", field="status.containerStatuses")
async def container_status_changed(old, new, name, namespace, **kwargs):
    if namespace not in ["applications"]:
        return

    if not new:
        return

    for container in new:
        restart_count = container.get("restartCount", 0)
        if restart_count >= 3:
            logger.info("🔁 CrashLoop detected on %s (restarts=%d)", name, restart_count)
            
            # FAST TRACK: Bypassing ML calls if pod is already in a severe restart loop (restores faster)
            if restart_count >= 5:
                logger.warning("🚀 FAST TRACK: Pod in severe CrashLoop (>=5), bypassing ML analysis for instant restart.")
                await restart_pod(name, namespace)
                return

            metrics = await get_pod_metrics(name, namespace)
            result = await analyze_with_ml(metrics)

            if result.get("is_anomaly") or restart_count >= 5:
                await restart_pod(name, namespace)

