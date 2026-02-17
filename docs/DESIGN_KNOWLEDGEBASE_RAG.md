# Knowledgebase Search (RAG) — Feature Design

## 1. Overview

Knowledgebase Search adds a **Retrieval-Augmented Generation (RAG)** pattern to our customer support agent using **Azure AI Search agentic retrieval**. The main agent gains a new `do_rag` tool that queries a knowledge base of order documents and return policies, retrieves grounding documents with citations, and uses them to formulate accurate answers.

**Key design choices:**
- **Agentic retrieval, retrieval-only mode** — the knowledge base returns verbatim extractive data (not pre-synthesized answers), allowing our main agent to reason over the raw content.
- **Minimal reasoning effort** — bypasses LLM-based query planning in Azure AI Search to reduce costs and latency. Our main agent handles query formulation.
- **Two knowledge sources** (two indexes): per-order detail documents, and a global return policy document.
- **Tool-based integration** — the main `CustomerSupportAgent` calls `do_rag` as a tool when it needs detailed order or policy information beyond what `get_order_status` provides.

```
┌────────────────────────────────┐          ┌─────────────────────────────────────────────┐
│  CustomerSupportAgent          │          │  Azure AI Search                            │
│  (Agent Framework ChatAgent)   │          │                                             │
│                                │  do_rag  │  ┌─────────────────────────────────────┐    │
│  Tools:                        │ ──────►  │  │  Knowledge Base                     │    │
│  • get_order_status            │          │  │  (output_mode=EXTRACTIVE_DATA)      │    │
│  • check_memory                │  ◄────── │  │  (reasoning_effort=minimal)         │    │
│  • do_rag  ←── NEW            │ citations│  │                                     │    │
│                                │ + chunks │  │  ┌─────────────┐ ┌───────────────┐  │    │
└────────────────────────────────┘          │  │  │ KS: Orders  │ │ KS: Policies  │  │    │
                                            │  │  │ (index)     │ │ (index)       │  │    │
                                            │  │  └─────────────┘ └───────────────┘  │    │
                                            │  └─────────────────────────────────────┘    │
                                            └─────────────────────────────────────────────┘
```

---

## 2. Azure AI Search Infrastructure

### 2.1 Terraform: New Resource (`infra/search.tf`)

Create an Azure AI Search service with semantic ranker enabled (required for agentic retrieval).

```hcl
resource "azurerm_search_service" "main" {
  name                          = "search-${var.project_name}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = var.location
  sku                           = "standard"                   # semantic ranker requires standard+
  semantic_search_sku           = "standard"                   # enables semantic ranker
  local_authentication_enabled  = false                        # Entra-only auth
  authentication_failure_mode   = "http403"

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}
```

> **Note:** Agentic retrieval is in public preview and requires a region that supports it. Check [region support](https://learn.microsoft.com/en-us/azure/search/search-region-support) and align with `var.location` (current default: `eastus2` — supported).

### 2.2 Terraform: New Variables (`infra/variables.tf`)

```hcl
variable "search_sku" {
  description = "Azure AI Search SKU (standard required for semantic ranker / agentic retrieval)"
  type        = string
  default     = "standard"
}
```

### 2.3 Terraform: Role Assignments (`infra/roles.tf`)

The managed identity used by the backend Container App needs access to Azure AI Search. The AI Search service's system-managed identity needs access to Azure OpenAI for query-time vectorization.

```hcl
# Search Index Data Reader — allows managed identity (backend app) to query indexes and knowledge bases
resource "azurerm_role_assignment" "mi_search_index_data_reader" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Search Service Contributor — allows managed identity (backend app) to call knowledge base retrieve
resource "azurerm_role_assignment" "mi_search_service_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Cognitive Services User — allows AI Search system identity to call Azure OpenAI for vectorization
resource "azurerm_role_assignment" "search_cognitive_services_user" {
  scope                = azapi_resource.ai_foundry.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_search_service.main.identity[0].principal_id
}
```

### 2.4 Terraform: Outputs (`infra/outputs.tf`)

```hcl
output "search_endpoint" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "search_name" {
  value = azurerm_search_service.main.name
}
```

### 2.5 New Environment Variables

```env
# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://search-mhaimem.search.windows.net
AZURE_SEARCH_ORDERS_INDEX=orders
AZURE_SEARCH_POLICIES_INDEX=return-policy
AZURE_SEARCH_KNOWLEDGE_BASE_NAME=customer-support-kb
```

---

## 3. Knowledge Base Architecture

### 3.1 Indexes

Two separate indexes hold different content types:

#### Index 1: `orders` — Per-Order Detail Documents

| Field | Type | Properties |
|-------|------|-----------|
| `id` | `Edm.String` | Key, filterable, sortable |
| `order_id` | `Edm.String` | Filterable, sortable, facetable |
| `page_chunk` | `Edm.String` | Searchable (main content) |
| `page_embedding` | `Collection(Edm.Single)` | Vector (3072 dims, text-embedding-3-large) |
| `category` | `Edm.String` | Filterable, facetable (e.g., "order_detail", "shipping", "product") |

Semantic configuration: `page_chunk` as content field.
Vector search: HNSW profile with `text-embedding-3-large` vectorizer pointing to our Azure OpenAI deployment.

#### Index 2: `return-policy` — Global Policy Documents

| Field | Type | Properties |
|-------|------|-----------|
| `id` | `Edm.String` | Key, filterable, sortable |
| `page_chunk` | `Edm.String` | Searchable (main content) |
| `page_embedding` | `Collection(Edm.Single)` | Vector (3072 dims, text-embedding-3-large) |
| `section` | `Edm.String` | Filterable (e.g., "eligibility", "process", "exceptions") |

Same semantic configuration and vector search profile.

### 3.2 Knowledge Sources

Two knowledge sources wrap the indexes:

```python
# Knowledge Source 1: Order Details
SearchIndexKnowledgeSource(
    name="orders-knowledge-source",
    description="Detailed order information including products, shipping, and payment details",
    search_index_parameters=SearchIndexKnowledgeSourceParameters(
        search_index_name="orders",
        source_data_fields=[
            SearchIndexFieldReference(name="id"),
            SearchIndexFieldReference(name="order_id"),
            SearchIndexFieldReference(name="category"),
        ]
    ),
)

# Knowledge Source 2: Return Policy
SearchIndexKnowledgeSource(
    name="policies-knowledge-source",
    description="Company return and refund policies, eligibility rules, and process steps",
    search_index_parameters=SearchIndexKnowledgeSourceParameters(
        search_index_name="return-policy",
        source_data_fields=[
            SearchIndexFieldReference(name="id"),
            SearchIndexFieldReference(name="section"),
        ]
    ),
)
```

### 3.3 Knowledge Base

A single knowledge base aggregates both sources and uses retrieval-only mode:

```python
KnowledgeBase(
    name="customer-support-kb",
    knowledge_sources=[
        KnowledgeSourceReference(name="orders-knowledge-source"),
        KnowledgeSourceReference(name="policies-knowledge-source"),
    ],
    output_mode=KnowledgeRetrievalOutputMode.EXTRACTIVE_DATA,        # retrieval-only
    retrieval_reasoning_effort=KnowledgeRetrievalMinimalReasoningEffort(),  # no LLM query planning
)
```

**Why retrieval-only + minimal reasoning effort?**
- Our main agent already formulates the query — no need for AI Search to do LLM-based query planning on top.
- Extractive data gives our agent raw content to reason over, preserving its ability to combine search results with tool outputs and conversation context.
- Reduces costs (no Azure OpenAI token usage within AI Search for query planning).

---

## 4. Sample Documents

### 4.1 Order Documents (`setup/knowledgebase/orders/`)

One JSON document per order, matching the three existing sample orders in `get_order_status`. Each document is chunked into logical sections.

#### `setup/knowledgebase/orders/ord-001.json`
```json
[
  {
    "id": "ord-001-overview",
    "order_id": "ORD-001",
    "category": "order_detail",
    "page_chunk": "Order ORD-001 was placed on January 15, 2026 by the customer. The order contains 2 items: (1) Wireless Noise-Cancelling Headphones (Model: WH-1000XM5, Color: Black, Qty: 1, Price: $349.99) and (2) USB-C Charging Cable 2m (Qty: 2, Price: $14.99 each). Order subtotal: $379.97. Shipping: $9.99 (Standard). Tax: $31.20. Order total: $421.16. Payment method: Visa ending in 4242."
  },
  {
    "id": "ord-001-shipping",
    "order_id": "ORD-001",
    "category": "shipping",
    "page_chunk": "Order ORD-001 was shipped on January 18, 2026 via UPS Ground. Tracking number: 1Z999AA1. The package was dispatched from the Seattle fulfillment center. Estimated delivery date: January 25, 2026. Shipping address: 123 Main Street, Apt 4B, Seattle, WA 98101. Current status: In transit — last scanned at Portland sorting facility on January 20, 2026."
  },
  {
    "id": "ord-001-product",
    "order_id": "ORD-001",
    "category": "product",
    "page_chunk": "Wireless Noise-Cancelling Headphones (WH-1000XM5): Premium over-ear headphones with industry-leading noise cancellation. Features include 30-hour battery life, multipoint Bluetooth connection, speak-to-chat automatic pause, adaptive sound control, and Hi-Res Audio support. Comes with carrying case, USB-C charging cable (included), and 3.5mm audio cable. Warranty: 1 year manufacturer warranty from date of delivery. Eligible for extended warranty purchase within 30 days of delivery."
  }
]
```

#### `setup/knowledgebase/orders/ord-002.json`
```json
[
  {
    "id": "ord-002-overview",
    "order_id": "ORD-002",
    "category": "order_detail",
    "page_chunk": "Order ORD-002 was placed on January 20, 2026 by the customer. The order contains 1 item: Ergonomic Office Chair (Model: ErgoMax Pro, Color: Gray Mesh, Qty: 1, Price: $599.00). Order subtotal: $599.00. Shipping: Free (orders over $500 qualify for free shipping). Tax: $49.12. Order total: $648.12. Payment method: Mastercard ending in 8888."
  },
  {
    "id": "ord-002-shipping",
    "order_id": "ORD-002",
    "category": "shipping",
    "page_chunk": "Order ORD-002 is currently being processed at the warehouse. Status: Processing. The item is a large/heavy shipment and requires freight handling. Estimated ship date: January 22, 2026. Estimated delivery date: January 28, 2026. Shipping method: Standard freight delivery. Shipping address: 456 Oak Avenue, Suite 200, Portland, OR 97201. Note: Freight deliveries require signature upon receipt and a delivery appointment will be scheduled by the carrier."
  },
  {
    "id": "ord-002-product",
    "order_id": "ORD-002",
    "category": "product",
    "page_chunk": "Ergonomic Office Chair (ErgoMax Pro): Professional-grade ergonomic chair with adjustable lumbar support, 4D armrests, breathable mesh back, and seat depth adjustment. Weight capacity: 300 lbs. Includes headrest attachment. Assembly required (estimated 45 minutes, tools included). Warranty: 5-year warranty covering frame, mechanism, and fabric. 30-day comfort guarantee — if not satisfied, return for full refund. Chair dimensions: 27\"W x 27\"D x 45-50\"H."
  }
]
```

#### `setup/knowledgebase/orders/ord-003.json`
```json
[
  {
    "id": "ord-003-overview",
    "order_id": "ORD-003",
    "category": "order_detail",
    "page_chunk": "Order ORD-003 was placed on January 10, 2026 by the customer. The order contains 3 items: (1) Mechanical Keyboard (Model: KeyPro TKL, Switch: Cherry MX Brown, Qty: 1, Price: $129.99), (2) Desk Mouse Pad XXL (900x400mm, Qty: 1, Price: $24.99), and (3) Webcam HD 1080p (Model: ClearView Pro, Qty: 1, Price: $79.99). Order subtotal: $234.97. Shipping: $5.99 (Standard). Tax: $19.28. Order total: $260.24. Payment method: PayPal (email: customer@email.com)."
  },
  {
    "id": "ord-003-shipping",
    "order_id": "ORD-003",
    "category": "shipping",
    "page_chunk": "Order ORD-003 was delivered on January 20, 2026. Tracking number: 1Z999AA3. Shipped via FedEx Ground from the Dallas fulfillment center on January 13, 2026. Delivery confirmed: signed by recipient at front door. Shipping address: 789 Pine Road, Austin, TX 78701. All 3 items were delivered in a single package."
  },
  {
    "id": "ord-003-product",
    "order_id": "ORD-003",
    "category": "product",
    "page_chunk": "Mechanical Keyboard (KeyPro TKL): Tenkeyless mechanical keyboard with Cherry MX Brown switches for a tactile, quiet typing experience. Features RGB per-key backlighting, USB-C detachable cable, PBT double-shot keycaps, and N-key rollover. Warranty: 2-year manufacturer warranty. Desk Mouse Pad XXL: Extended mouse pad (900x400mm) with micro-weave cloth surface and non-slip rubber base. Machine washable. Warranty: 6-month warranty. Webcam HD 1080p (ClearView Pro): Full HD webcam with auto-focus, built-in dual microphones, and privacy shutter. Compatible with all major video conferencing platforms. Warranty: 1-year warranty."
  }
]
```

### 4.2 Return Policy Document (`setup/knowledgebase/policies/return-policy.json`)

```json
[
  {
    "id": "policy-eligibility",
    "section": "eligibility",
    "page_chunk": "Return Eligibility Policy: Items may be returned within 30 days of delivery for a full refund. Products must be in their original packaging, unused, and in resalable condition. Electronics must include all original accessories, cables, and documentation. Opened software, downloadable products, and gift cards are non-returnable. Items marked as 'Final Sale' at the time of purchase cannot be returned. Furniture items (including office chairs and desks) have a 30-day comfort guarantee and may be returned even if assembled, provided they are in good condition."
  },
  {
    "id": "policy-process",
    "section": "process",
    "page_chunk": "Return Process: To initiate a return, contact customer support with your order ID and reason for return. A Return Merchandise Authorization (RMA) number will be issued within 1 business day. Pack the item securely in its original packaging (or equivalent protective packaging). Affix the prepaid return shipping label (provided via email after RMA approval). Drop off the package at any authorized carrier location. Standard return shipping is free for defective items. For non-defective returns, a $7.99 return shipping fee is deducted from the refund. Freight items (over 50 lbs) require scheduled carrier pickup — customer support will arrange this at no additional cost."
  },
  {
    "id": "policy-refunds",
    "section": "refunds",
    "page_chunk": "Refund Policy: Refunds are processed within 5-7 business days after the returned item is received and inspected at our facility. Refunds are issued to the original payment method. Credit card refunds may take an additional 3-5 business days to appear on your statement. PayPal refunds are typically reflected within 1-2 business days. If the item is returned in damaged or used condition, a restocking fee of up to 15% may be applied. For defective items, a full refund is issued including original shipping charges. Exchange option: instead of a refund, customers may request a direct exchange for the same item (different color/size) or store credit valued at 110% of the purchase price."
  },
  {
    "id": "policy-exceptions",
    "section": "exceptions",
    "page_chunk": "Return Exceptions and Special Cases: Holiday purchases (November 15 – December 31) have an extended return window until January 31 of the following year. Warranty claims beyond the 30-day return window are handled separately through the manufacturer warranty process — contact support with your order ID and proof of defect. Bulk orders (10+ units of the same item) have a modified return policy: up to 20% of the order quantity may be returned within 30 days; larger returns require manager approval. International orders: return shipping is the customer's responsibility; customs duties paid are non-refundable. Price adjustment: if an item's price drops within 14 days of your purchase, contact support for a price match credit."
  }
]
```

### 4.3 Document File Structure

```
setup/
  knowledgebase/
    README.md                          # How to run the setup scripts
    documents/
      orders/
        ord-001.json
        ord-002.json
        ord-003.json
      policies/
        return-policy.json
    setup_search.py                    # One-time script: create indexes, upload docs,
                                       # create knowledge sources + knowledge base
```

---

## 5. Setup Script (`setup/knowledgebase/setup_search.py`)

A one-time Python script that provisions the AI Search knowledge base end-to-end. Uses the `azure-search-documents` SDK (preview version with agentic retrieval support).

### 5.1 Script Flow

```
1. Load environment variables (.env)
2. Authenticate with DefaultAzureCredential
3. Create "orders" search index (schema + semantic config + vector search)
4. Create "return-policy" search index (same pattern)
5. Upload order documents from setup/knowledgebase/documents/orders/*.json
6. Upload policy documents from setup/knowledgebase/documents/policies/*.json
7. Create knowledge source: "orders-knowledge-source" → orders index
8. Create knowledge source: "policies-knowledge-source" → return-policy index
9. Create knowledge base: "customer-support-kb" with both sources
10. Print the knowledge base MCP endpoint (informational)
```

### 5.2 Required Environment Variables

```env
AZURE_SEARCH_ENDPOINT=https://search-mhaimem.search.windows.net
AZURE_OPENAI_ENDPOINT=https://aifoundry-mhaimem.openai.azure.com
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
```

### 5.3 Dependencies

Add to a `setup/knowledgebase/requirements.txt`:

```
azure-search-documents==11.7.0b2
azure-identity
python-dotenv
```

These are **setup-only** dependencies (not needed by the running backend).

### 5.4 Index Schema Pattern (both indexes follow this pattern)

```python
SearchIndex(
    name=index_name,
    fields=[
        SearchField(name="id", type="Edm.String", key=True, filterable=True, sortable=True),
        SearchField(name="page_chunk", type="Edm.String", filterable=False, sortable=False),
        SearchField(name="page_embedding", type="Collection(Edm.Single)",
                    stored=False,
                    vector_search_dimensions=3072,
                    vector_search_profile_name="hnsw_text_3_large"),
        # ... additional fields per index (order_id, category, section, etc.)
    ],
    vector_search=VectorSearch(
        profiles=[VectorSearchProfile(
            name="hnsw_text_3_large",
            algorithm_configuration_name="alg",
            vectorizer_name="azure_openai_text_3_large",
        )],
        algorithms=[HnswAlgorithmConfiguration(name="alg")],
        vectorizers=[AzureOpenAIVectorizer(
            vectorizer_name="azure_openai_text_3_large",
            parameters=AzureOpenAIVectorizerParameters(
                resource_url=azure_openai_endpoint,
                deployment_name=embedding_deployment,
                model_name="text-embedding-3-large",
            ),
        )],
    ),
    semantic_search=SemanticSearch(
        default_configuration_name="semantic_config",
        configurations=[SemanticConfiguration(
            name="semantic_config",
            prioritized_fields=SemanticPrioritizedFields(
                content_fields=[SemanticField(field_name="page_chunk")],
            ),
        )],
    ),
)
```

> **Note on vectorization:** The index uses **integrated vectorization** via the `AzureOpenAIVectorizer` configured on the index. This means:
> - At indexing time, we do NOT need to pre-compute embeddings — upload plain text and AI Search calls the embedding model.
> - At query time, text queries are automatically vectorized using the same model.
> - The AI Search service's system-managed identity must have `Cognitive Services User` role on the Azure OpenAI resource (handled in role assignments above).
>
> However, the `SearchIndexingBufferedSender` used for document upload does **not** automatically vectorize. Documents must either include pre-computed embeddings or we use an indexer with a skillset. For simplicity in this setup script, we will **omit the `page_embedding` field from the uploaded documents** and rely on a pull-indexer with a built-in vectorization skill, OR we manually compute embeddings during upload. The design recommends **manual embedding computation during upload** to keep the setup self-contained without requiring indexers or skillsets.

---

## 6. Backend: `do_rag` Tool

### 6.1 Architecture

The `do_rag` tool is a new `@tool`-decorated function in `server.py` that calls the Azure AI Search knowledge base retrieve API. It acts as a bridge between the main agent and the knowledge base.

```
Main Agent receives user query
    │
    ├─ Agent decides it needs knowledge base info
    │   (e.g., user asks about return policy, order details, product warranty)
    │
    ▼
do_rag(query="return policy for opened electronics") is called
    │
    ▼
Backend calls AI Search Knowledge Base Retrieve API:
    POST {search_endpoint}/knowledgebases/customer-support-kb/retrieve?api-version=2025-11-01-Preview
    {
      "messages": [
        { "role": "user", "content": "return policy for opened electronics" }
      ]
    }
    │
    ▼
AI Search returns extractive data:
    - grounding content (page_chunk text)
    - citations (source document IDs, field references)
    │
    ▼
do_rag formats results as a string and returns to the main agent
    │
    ▼
Main Agent interprets grounding data and formulates final answer with citations
```

### 6.2 Tool Definition

```python
@tool
async def do_rag(
    query: Annotated[str, Field(description="Natural-language query to search the knowledge base for order details, product information, or company policies")],
) -> str:
    """Search the company knowledge base for detailed order information, product
    specifications, shipping details, and return/refund policies.

    Use this tool when the user asks about:
    - Detailed order contents, pricing, or payment information
    - Product specifications, warranties, or features
    - Return, refund, or exchange policies
    - Shipping methods, costs, or delivery details
    - Any factual question that requires looking up company documentation

    Returns relevant document excerpts with source citations.
    """
```

### 6.3 Knowledge Base Retrieve API Call

The tool calls the AI Search knowledge base retrieve REST API directly (the Python SDK also supports this via `SearchIndexClient`):

```python
POST {AZURE_SEARCH_ENDPOINT}/knowledgebases/customer-support-kb/retrieve?api-version=2025-11-01-Preview
Authorization: Bearer {token}
Content-Type: application/json

{
  "messages": [
    { "role": "user", "content": "{query}" }
  ]
}
```

**Response structure (simplified):**
```json
{
  "response": {
    "content": "... merged grounding text from all matching chunks ...",
    "citations": [
      {
        "content": "Order ORD-001 was placed on January 15...",
        "id": "ord-001-overview",
        "fields": { "order_id": "ORD-001", "category": "order_detail" }
      }
    ]
  },
  "activity": [ ... query execution details ... ]
}
```

### 6.4 Response Formatting

The tool returns a formatted string to the agent:

```python
async def do_rag(query: ...) -> str:
    # ... call retrieve API ...
    
    # Format results for the agent
    parts = []
    parts.append(f"Knowledge Base Results for: {query}")
    parts.append("=" * 40)
    
    if response.content:
        parts.append(f"\nGrounding Content:\n{response.content}")
    
    if response.citations:
        parts.append(f"\nSources ({len(response.citations)} documents):")
        for i, citation in enumerate(response.citations, 1):
            source_info = []
            if citation.fields.get("order_id"):
                source_info.append(f"Order: {citation.fields['order_id']}")
            if citation.fields.get("section"):
                source_info.append(f"Section: {citation.fields['section']}")
            if citation.fields.get("category"):
                source_info.append(f"Category: {citation.fields['category']}")
            parts.append(f"  [{i}] {citation.id} ({', '.join(source_info)})")
    
    if not response.content and not response.citations:
        return "No relevant information found in the knowledge base."
    
    return "\n".join(parts)
```

### 6.5 New Module: `backend/rag_client.py`

A thin client class to encapsulate the AI Search knowledge base interaction:

```
class RAGClient:
    """Client for Azure AI Search agentic retrieval (knowledge base retrieve API)."""

    def __init__(
        self,
        search_endpoint: str,
        knowledge_base_name: str,
        credential: DefaultAzureCredential,
    )

    async def retrieve(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> RAGResult:
        """
        Call the knowledge base retrieve API.
        
        Args:
            query: Natural language query
            conversation_history: Optional chat history for context
            
        Returns:
            RAGResult(content, citations)
        """

@dataclass
class RAGCitation:
    content: str
    id: str
    fields: dict[str, str]

@dataclass
class RAGResult:
    content: str                    # merged grounding text
    citations: list[RAGCitation]    # source document references
```

**Implementation details:**
- Uses `aiohttp` (already a dependency) to call the REST API directly.
- Authenticates with `DefaultAzureCredential` → bearer token for `https://search.azure.com/.default` scope.
- API version: `2025-11-01-Preview` (required for agentic retrieval).
- Alternatively, can use `azure-search-documents==11.7.0b2` Python SDK's `SearchIndexClient.retrieve_from_knowledge_base()` method if available. The REST approach is more explicit and less dependent on SDK preview stability.

### 6.6 New Dependencies

Add to `backend/pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "azure-search-documents>=11.7.0b2",  # optional: if using SDK instead of REST
]
```

> **Decision: REST vs SDK.** The agentic retrieval SDK surface is `11.7.0b2` (preview). For stability, the design recommends using **direct REST calls** with `aiohttp` (already a dependency) for the retrieve API, and using the **SDK** only in the setup script (one-time). This avoids adding a preview SDK dependency to the production backend.

---

## 7. Prompt Update (`backend/prompts/customer_support.j2`)

### 7.1 Updated Prompt

Add the `do_rag` tool instructions to the existing system prompt:

```jinja2
You are a helpful customer support assistant.

You have access to the following tools:

1. **get_order_status** — Quick status lookup for an order.
   When a user mentions an order ID (like ORD-001, ORD-002, etc.),
   call this tool to retrieve the current order status.

2. **check_memory** — Search past conversation memories.
   When the user explicitly references or asks about something from a
   previous conversation, call this tool. Only use when the user
   explicitly asks about past conversations.

3. **do_rag** — Search the company knowledge base.
   Use this tool when the user asks about:
   - Detailed order contents, pricing, payment information, or product specs
   - Product warranties, features, or compatibility
   - Return, refund, or exchange policies and processes
   - Shipping methods, costs, estimated delivery details
   - Any question requiring factual company documentation

   IMPORTANT: When do_rag returns results, always reference the source
   citations in your response. Format citations naturally, e.g.:
   "According to our return policy, items may be returned within 30 days
   of delivery [Source: policy-eligibility]."

   Do NOT make up policy details or product specifications — always
   verify via do_rag when in doubt.

After calling any tool, provide the actual results to the user in a friendly format.

Remember the conversation context - if user refers to "it" or "the order",
they are referring to previously discussed orders in this conversation.
{%- if user_profile is defined and user_profile %}

== USER PROFILE ==
{# ... existing user profile section unchanged ... #}
{%- endif %}
```

### 7.2 Key Prompt Design Decisions

- **Citation format**: The agent is instructed to include `[Source: document_id]` citations in its responses. This grounds answers in the retrieved documents and builds user trust.
- **Tool selection guidance**: Clear rules for when to use `do_rag` vs `get_order_status` — the status tool is for quick status checks; `do_rag` is for detailed information, policies, and product data.
- **No fabrication**: The prompt strongly discourages making up policy or product details, directing the agent to always verify via `do_rag`.

---

## 8. Server Integration (`server.py`)

### 8.1 Initialization

```python
from rag_client import RAGClient

# Initialize the RAG client (after credential setup)
rag_client = RAGClient(
    search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
    knowledge_base_name=os.getenv("AZURE_SEARCH_KNOWLEDGE_BASE_NAME", "customer-support-kb"),
    credential=DefaultAzureCredential(),
)
```

No lifespan changes needed — the RAG client is stateless (creates HTTP sessions per-request or uses a shared `aiohttp.ClientSession`).

### 8.2 Tool Registration

Add `do_rag` to the agent's tool list:

```python
agent = ChatAgent(
    name="CustomerSupportAgent",
    instructions=CUSTOMER_SUPPORT_PROMPT,
    chat_client=chat_client,
    tools=[get_order_status, check_memory, do_rag],  # ← do_rag added
)
```

Also update `_build_personalized_agent`:

```python
def _build_personalized_agent(user_profile):
    if not user_profile:
        return agent
    personalized_prompt = load_prompt("customer_support.j2", user_profile=user_profile)
    return ChatAgent(
        name="CustomerSupportAgent",
        instructions=personalized_prompt,
        chat_client=chat_client,
        tools=[get_order_status, check_memory, do_rag],  # ← do_rag added
    )
```

### 8.3 No New API Endpoints

The RAG functionality is consumed exclusively through the main agent's tool calling mechanism. The frontend does not call AI Search directly. No new REST endpoints are needed.

---

## 9. Data Flow Diagrams

### 9.1 RAG Query Flow

```
User sends message: "What is the return policy for electronics?"
    │
    ▼
Frontend: POST /chat { messages: [...], thread_id: "..." }
    │
    ▼
Backend (server.py): stream_agent_response()
    │
    ▼
CustomerSupportAgent receives message
    ├─ Agent determines: this is a policy question → call do_rag
    │
    ▼
do_rag(query="return policy for electronics")
    │
    ▼
RAGClient.retrieve(query="return policy for electronics")
    ├─ POST {search_endpoint}/knowledgebases/customer-support-kb/retrieve
    │       Body: { "messages": [{ "role": "user", "content": "..." }] }
    │
    ▼
AI Search Knowledge Base:
    ├─ Searches across both indexes (orders + return-policy)
    ├─ Runs hybrid search (text + vector via integrated vectorization)
    ├─ Applies semantic ranking
    └─ Returns extractive data + citations
    │
    ▼
do_rag formats response string with grounding content + citations
    │
    ▼
CustomerSupportAgent receives tool result
    ├─ Interprets grounding content
    ├─ Formulates natural-language answer
    ├─ Includes source citations
    └─ Streams response to user via AG-UI events
    │
    ▼
Frontend displays assistant response with citations
```

### 9.2 Setup / Indexing Flow (One-Time)

```
Admin runs: python setup/knowledgebase/setup_search.py
    │
    ▼
1. Create "orders" index (schema + semantic config + vectorizer)
2. Create "return-policy" index (same pattern)
    │
    ▼
3. Read documents from setup/knowledgebase/documents/orders/*.json
4. For each document chunk:
    ├─ Compute embedding via Azure OpenAI text-embedding-3-large
    └─ Upload document with embedding to "orders" index
5. Read documents from setup/knowledgebase/documents/policies/*.json
6. Same: compute embedding + upload to "return-policy" index
    │
    ▼
7. Create knowledge source: "orders-knowledge-source"
8. Create knowledge source: "policies-knowledge-source"
    │
    ▼
9. Create knowledge base: "customer-support-kb"
    ├─ Sources: [orders-knowledge-source, policies-knowledge-source]
    ├─ Output mode: EXTRACTIVE_DATA
    └─ Reasoning effort: minimal
    │
    ▼
10. Print KB endpoint and summary
    Done — backend can now call retrieve API
```

---

## 10. File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `infra/search.tf` | **New** | Azure AI Search service resource + semantic ranker |
| `infra/variables.tf` | **Modify** | Add `search_sku` variable |
| `infra/roles.tf` | **Modify** | Add Search Index Data Reader + Search Service Contributor for MI, Cognitive Services User for Search MI |
| `infra/outputs.tf` | **Modify** | Add `search_endpoint`, `search_name` outputs |
| `setup/knowledgebase/README.md` | **New** | Setup instructions |
| `setup/knowledgebase/setup_search.py` | **New** | One-time script: create indexes, upload docs, create KB |
| `setup/knowledgebase/requirements.txt` | **New** | Setup script dependencies |
| `setup/knowledgebase/documents/orders/ord-001.json` | **New** | Order ORD-001 detail documents |
| `setup/knowledgebase/documents/orders/ord-002.json` | **New** | Order ORD-002 detail documents |
| `setup/knowledgebase/documents/orders/ord-003.json` | **New** | Order ORD-003 detail documents |
| `setup/knowledgebase/documents/policies/return-policy.json` | **New** | Return/refund policy documents |
| `backend/rag_client.py` | **New** | `RAGClient` — async client for AI Search KB retrieve API |
| `backend/server.py` | **Modify** | Add `do_rag` tool, initialize `RAGClient`, register tool on agents |
| `backend/prompts/customer_support.j2` | **Modify** | Add `do_rag` tool instructions and citation guidance |

---

## 11. Authentication & Security

| Communication Path | Auth Method |
|-------------------|-------------|
| Backend → AI Search (retrieve API) | `DefaultAzureCredential` → bearer token (`https://search.azure.com/.default`) |
| AI Search → Azure OpenAI (vectorization) | AI Search system-managed identity → Cognitive Services User role |
| Setup script → AI Search (management) | `DefaultAzureCredential` (developer identity) |
| Setup script → Azure OpenAI (embeddings) | `DefaultAzureCredential` (developer identity) |
| Frontend → Backend | Existing Entra ID auth (no change) |

Local development: The developer must be signed in via `az login` and have `Search Service Contributor` + `Search Index Data Contributor` roles on the AI Search service.

---

## 12. Open Questions / Future Considerations

1. **SDK vs REST for retrieve API:** The design recommends REST for the production backend to avoid a preview SDK dependency. If `azure-search-documents` stabilizes the agentic retrieval surface, switching to the SDK would simplify the code.

2. **Conversation context in retrieve calls:** The knowledge base retrieve API accepts a `messages` array (chat history). Currently, `do_rag` sends only the single query. A future enhancement could pass recent conversation turns for better context-aware retrieval.

3. **MCP integration:** The Azure AI Search knowledge base exposes an MCP endpoint. If the project later adopts Foundry Agent Service or MCP tooling, the knowledge base can be connected via MCP instead of direct REST calls. The current design keeps it simpler with direct API calls.

4. **Document updates:** When sample orders change or new orders are added, the setup script must be re-run to update the index. A future improvement could use AI Search indexers with a data source (Blob Storage, Cosmos DB) for automatic incremental indexing.

5. **Result size / token usage:** Extractive data from the knowledge base can be large. Consider setting `maxOutputSize` on the retrieve call to limit response size and control token consumption by the main agent.

6. **Cost considerations:**
   - AI Search `standard` SKU is required for semantic ranker (~$249/month).
   - Agentic retrieval tokens: 50M free tokens/month on standard plan.
   - Azure OpenAI embedding costs for vectorization (both setup and query-time).
   - Minimal reasoning effort avoids additional LLM costs within AI Search.

7. **Separate indexes vs single merged index:** The design uses two indexes (orders, policies) for logical separation and to demonstrate multi-source knowledge bases. For a simpler setup, they could be merged into one index with a `document_type` filter field.

8. **Integrated vectorization at query time:** With the `AzureOpenAIVectorizer` configured on the indexes, AI Search automatically vectorizes text queries. This means the `do_rag` tool sends plain text and gets hybrid (keyword + vector) results without needing to call the embedding API separately in the backend.
