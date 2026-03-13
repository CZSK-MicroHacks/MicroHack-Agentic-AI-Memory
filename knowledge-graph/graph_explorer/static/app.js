const statusBanner = document.getElementById("status-banner");
const searchInput = document.getElementById("search-input");
const searchButton = document.getElementById("search-button");
const searchResults = document.getElementById("search-results");
const nodeInput = document.getElementById("node-input");
const depthSelect = document.getElementById("depth-select");
const relationshipSelect = document.getElementById("relationship-select");
const exploreButton = document.getElementById("explore-button");
const cypherOutput = document.getElementById("cypher-output");
const exampleButtons = document.getElementById("example-buttons");
const nodeDetails = document.getElementById("node-details");
const followSelectedButton = document.getElementById("follow-selected-button");

const graphContainer = document.getElementById("graph");
let nodes;
let edges;
let network;

const state = {
  selectedNodeId: null,
  lastGraphPayload: null,
};

const TYPE_STYLES = {
  drug: { color: "#2563eb", shape: "dot" },
  disease: { color: "#dc2626", shape: "dot" },
  gene: { color: "#7c3aed", shape: "diamond" },
  symptom: { color: "#ea580c", shape: "triangle" },
  pathway: { color: "#059669", shape: "hexagon" },
  concept: { color: "#0f766e", shape: "star" },
  unknown: { color: "#64748b", shape: "dot" },
};

function setStatus(message, tone = "info") {
  statusBanner.textContent = message;
  statusBanner.dataset.tone = tone;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function encodeQuery(params) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, value);
    }
  });
  return searchParams.toString();
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail || "Request failed.";
    throw new Error(detail);
  }
  return payload;
}

function renderCypher(queries = []) {
  if (!queries.length) {
    cypherOutput.textContent = "No Cypher generated yet.";
    return;
  }
  cypherOutput.textContent = queries.map((query, index) => `-- Query ${index + 1}\n${query}`).join("\n\n");
}

function renderNodeDetails(details, { highlight = false, followable = true } = {}) {
  if (!details) {
    nodeDetails.innerHTML = "<p>Select a node in the graph to inspect it here.</p>";
    state.selectedNodeId = null;
    followSelectedButton.disabled = true;
    return;
  }

  const communities = (details.communities || [])
    .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
    .join("");

  nodeDetails.innerHTML = `
    <article class="detail-stack ${highlight ? "highlight" : ""}">
      <p class="eyebrow">${escapeHtml(details.node_type || "unknown")}</p>
      <h3>${escapeHtml(details.name)}</h3>
      <p>${escapeHtml(details.description || "No description available.")}</p>
      <div class="detail-section">
        <strong>Communities</strong>
        <div class="chip-row">${communities || "<span class='muted'>No community memberships found.</span>"}</div>
      </div>
    </article>
  `;

  state.selectedNodeId = followable ? details.name : null;
  followSelectedButton.disabled = !followable;
}

function upsertGraph(payload) {
  state.lastGraphPayload = payload;
  nodes.clear();
  edges.clear();
  mergeGraph(payload);
}

function mergeGraph(payload) {
  payload.nodes.forEach((node) => {
    if (nodes.get(node.id)) return;
    const style = TYPE_STYLES[node.node_type] || TYPE_STYLES.unknown;
    nodes.add({
      id: node.id,
      label: node.label,
      title: `${node.label}\n${node.node_type}`,
      color: {
        background: style.color,
        border: node.is_focus ? "#111827" : style.color,
        highlight: {
          background: style.color,
          border: "#111827",
        },
      },
      shape: style.shape,
      size: node.is_focus ? 28 : node.is_path ? 24 : 18,
      font: {
        color: "#111827",
      },
    });
  });

  payload.edges.forEach((edge) => {
    if (edges.get(edge.id)) return;
    edges.add({
      id: edge.id,
      from: edge.from,
      to: edge.to,
      label: edge.label,
      arrows: edge.arrows || "to",
    });
  });

  network.fit({
    animation: true,
    nodes: payload.nodes.map((node) => node.id),
  });
}

async function loadExamples() {
  const payload = await fetchJson("/api/examples");
  relationshipSelect.innerHTML = '<option value="">All relationships</option>';
  payload.relationship_types.forEach((relationshipType) => {
    const option = document.createElement("option");
    option.value = relationshipType;
    option.textContent = relationshipType;
    relationshipSelect.appendChild(option);
  });

  exampleButtons.innerHTML = "";
  payload.sample_nodes.forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "example-chip";
    button.textContent = example.name;
    button.title = example.node_type;
    button.addEventListener("click", () => {
      nodeInput.value = example.name;
      exploreNeighborhood(example.name);
    });
    exampleButtons.appendChild(button);
  });

  setStatus("Ready to explore.", "success");
}

async function runSearch() {
  const query = searchInput.value.trim();
  if (!query) {
    setStatus("Enter a search term first.", "warning");
    return;
  }

  setStatus(`Searching for "${query}"…`);
  const payload = await fetchJson(`/api/search?${encodeQuery({ query })}`);
  searchResults.innerHTML = "";

  if (!payload.results.length) {
    searchResults.innerHTML = "<p class='muted'>No matching nodes found.</p>";
    setStatus("No matching nodes found.", "warning");
    return;
  }

  payload.results.forEach((result) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-result";
    button.innerHTML = `<strong>${escapeHtml(result.name)}</strong><span>${escapeHtml(result.node_type)}</span><small>${escapeHtml(result.description)}</small>`;
    button.addEventListener("click", () => {
      nodeInput.value = result.name;
      exploreNeighborhood(result.name);
    });
    searchResults.appendChild(button);
  });

  setStatus(`Found ${payload.results.length} matching node(s).`, "success");
}

async function exploreNeighborhood(explicitNodeName) {
  const name = (explicitNodeName || nodeInput.value).trim();
  if (!name) {
    setStatus("Choose a node name first.", "warning");
    return;
  }

  setStatus(`Loading ${name}'s neighborhood…`);
  const payload = await fetchJson(`/api/node?${encodeQuery({
    name,
    depth: depthSelect.value,
    relationship_type: relationshipSelect.value,
  })}`);

  upsertGraph(payload);
  renderCypher(payload.cypher_queries);
  renderNodeDetails(payload.details, { highlight: true });
  nodeInput.value = name;
  setStatus(`Loaded ${payload.nodes.length} node(s) around ${name}.`, "success");
}

function initializeNetwork() {
  nodes = new vis.DataSet([]);
  edges = new vis.DataSet([]);
  network = new vis.Network(
    graphContainer,
    { nodes, edges },
    {
      autoResize: true,
      interaction: {
        dragNodes: true,
        hover: true,
        multiselect: false,
        navigationButtons: true,
      },
      physics: {
        stabilization: true,
        barnesHut: {
          gravitationalConstant: -2500,
          springLength: 150,
        },
      },
      nodes: {
        shape: "dot",
        size: 18,
        borderWidth: 2,
        font: {
          face: "Segoe UI, sans-serif",
          size: 14,
        },
      },
      edges: {
        width: 2,
        arrows: {
          to: {
            enabled: true,
            scaleFactor: 0.7,
          },
        },
        font: {
          align: "middle",
          strokeWidth: 3,
          strokeColor: "#ffffff",
        },
        smooth: {
          type: "dynamic",
        },
      },
    }
  );

  network.on("click", async (event) => {
    if (!event.nodes.length) {
      return;
    }
    const nodeId = event.nodes[0];
    try {
      const payload = await fetchJson(`/api/node?${encodeQuery({
        name: nodeId,
        depth: 1,
        relationship_type: relationshipSelect.value,
      })}`);
      mergeGraph(payload);
      renderNodeDetails(payload.details);
      renderCypher(payload.cypher_queries || []);
      setStatus(`Expanded ${nodeId} – ${nodes.length} node(s) on canvas.`, "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });
}

followSelectedButton.addEventListener("click", () => {
  if (!state.selectedNodeId) {
    return;
  }
  nodeInput.value = state.selectedNodeId;
  exploreNeighborhood(state.selectedNodeId).catch((error) => {
    setStatus(error.message, "error");
  });
});

searchButton.addEventListener("click", () => {
  runSearch().catch((error) => {
    setStatus(error.message, "error");
  });
});

exploreButton.addEventListener("click", () => {
  exploreNeighborhood().catch((error) => {
    setStatus(error.message, "error");
  });
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runSearch().catch((error) => {
      setStatus(error.message, "error");
    });
  }
});

nodeInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    exploreNeighborhood().catch((error) => {
      setStatus(error.message, "error");
    });
  }
});

window.addEventListener("load", async () => {
  if (!window.vis) {
    setStatus("vis-network failed to load. Check internet access for the CDN asset.", "error");
    return;
  }

  initializeNetwork();

  try {
    await loadExamples();
  } catch (error) {
    setStatus(error.message, "error");
  }
});
