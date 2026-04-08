async function loadHealth() {
  const healthValue = document.querySelector("[data-health-value]");
  const envValue = document.querySelector("[data-env-value]");

  try {
    const response = await fetch("/api/health");
    const data = await response.json();

    healthValue.textContent = data.status === "ok" ? "Online" : data.status;
    envValue.textContent = data.env;
  } catch (error) {
    healthValue.textContent = "Unavailable";
    envValue.textContent = "unknown";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void loadHealth();
});
