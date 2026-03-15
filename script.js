let showBlocked = true; // Blocked list is shown initially
let lastBlockedNotification = null;

// Fetch and display logs
async function fetchTrafficLogs() {
  try {
    const trafficResponse = await fetch("traffic_log.json");
    const filteredResponse = await fetch("filtered_traffic_log.json");

    if (!trafficResponse.ok || !filteredResponse.ok) {
      throw new Error("Failed to fetch logs");
    }

    const trafficData = await trafficResponse.json();
    const filteredData = await filteredResponse.json();

    // Always update both containers
    displayLogs(trafficData.reverse(), "normalTraffic", false);
    displayLogs(filteredData.reverse(), "blockedTraffic", true);

    // Notify if a new blocked site is visited
    if (
      filteredData.length > 0 &&
      (!lastBlockedNotification ||
        new Date(filteredData[0].timestamp) > new Date(lastBlockedNotification))
    ) {
      lastBlockedNotification = filteredData[0].timestamp;
      alert(`Blocked site visited: ${filteredData[0].url}`);
    }
  } catch (error) {
    console.error("Error fetching data:", error);
    document.getElementById("normalTraffic").textContent =
      "Failed to load traffic log.";
    document.getElementById("blockedTraffic").textContent =
      "Failed to load filtered traffic log.";
  }
}

// Display logs in containers
function displayLogs(data, containerId, isBlocked) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  data.forEach((entry) => {
    const entryDiv = document.createElement("div");
    entryDiv.className = "entry";
    if (isBlocked) entryDiv.classList.add("blocked");

    const timestampDiv = document.createElement("div");
    timestampDiv.className = "timestamp";
    timestampDiv.textContent = `Timestamp: ${entry.timestamp}`;

    const urlDiv = document.createElement("a");
    urlDiv.className = "url";
    urlDiv.href = entry.url;
    urlDiv.textContent = entry.url;
    urlDiv.target = "_blank";

    entryDiv.appendChild(timestampDiv);
    entryDiv.appendChild(urlDiv);

    container.appendChild(entryDiv);
  });
}

// Toggle between normal and blocked traffic logs
function toggleLogs() {
  const normalTraffic = document.getElementById("normalTraffic");
  const blockedTraffic = document.getElementById("blockedTraffic");
  const button = document.querySelector(".toggle-button");

  if (showBlocked) {
    // Show normal traffic log
    blockedTraffic.style.display = "none";
    normalTraffic.style.display = "block";
    button.textContent = "Show Alerted Sites";
  } else {
    // Show blocked site log
    normalTraffic.style.display = "none";
    blockedTraffic.style.display = "block";
    button.textContent = "Show Active History Log";
  }

  showBlocked = !showBlocked; // Toggle the state
}

// Fetch data every 5 seconds
setInterval(fetchTrafficLogs, 5000);

// Initial fetch and set default state
fetchTrafficLogs();
document.getElementById("blockedTraffic").style.display = "block"; // Show blocked log initially
