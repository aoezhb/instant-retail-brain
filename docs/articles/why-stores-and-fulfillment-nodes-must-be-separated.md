# Why Stores and Fulfillment Nodes Must Be Separate

In an early instant-retail dataset, a store and an inventory location often appear to have a one-to-one relationship. One store owns one stock position and fulfills its own orders. Reusing one identifier for both may look simpler, but it mixes the sales relationship with the inventory relationship. Shared warehouses, multiple fulfillment options, split orders, and routing changes then become difficult to represent.

The shortest useful distinction is:

- A store answers where demand occurred and who operated the sale.
- A fulfillment node answers where inventory was held and where fulfillment occurred.
- A business unit answers which operating and accounting structure owns the stores and nodes.

## Different Objects, Different Responsibilities

| Object | Main records | Question answered |
|---|---|---|
| Business unit | Ownership, operating rules, accounting definitions | Which entity owns purchasing, inventory, and results |
| Store | Sales, customers, assortment, price, promotion | Which selling location generated demand |
| Fulfillment node | Available stock, inbound stock, reservations, backorders, service area | Which inventory location satisfies demand |

A store is a demand observation level. A fulfillment node is an inventory and execution level. A current one-to-one mapping does not make them the same object.

## Why a One-to-One Mapping Still Needs Its Own Record

Relationships change while object identities should remain stable.

~~~mermaid
flowchart LR
    S1[Store A] --> N1[Node 1]
    S2[Store B] --> N1
    S3[Store C] --> N2[Node 2]
    S3 -.peak period.-> N1
~~~

Typical changes include:

1. One dark store serves several online stores.
2. A store changes node according to distance, stock, or delivery capacity.
3. One order is split across more than one node.
4. A store closes while its node continues serving other stores.
5. Different business units reuse the same local store or node identifier.

If a store identifier was also used as the node identifier, these changes require primary-key changes across demand, inventory, prediction, and history instead of a new relationship record.

## What Goes Wrong When They Are Combined

### Demand and inventory cannot be aggregated correctly

A store forecast describes selling demand. Node replenishment requires the total demand assigned to that node. When one node serves several stores, store forecasts must be allocated and aggregated before replenishment is calculated.

### Inventory may be counted more than once

If several stores share one node and each store receives a copied stock balance, the same physical inventory appears multiple times and produces false availability.

### Historical changes cannot be represented

When a store changes fulfillment node, its sales history still belongs to the store while inventory and fulfillment belong to the node used at that time. Separate identities preserve both facts during historical replay.

### The target of a decision becomes unclear

A replenishment decision must identify the node receiving stock. Assortment and pricing advice often targets a store. A single identifier does not reliably say which object should receive the action.

## How This Repository Represents Them

The project defines <code>BusinessUnit</code>, <code>Store</code>, <code>FulfillmentNode</code>, and <code>StoreNodeBinding</code> separately. A store-to-node mapping is an explicit record rather than an inference based on equal identifiers.

The runtime item key is:

~~~text
ItemKey = (
    business_unit_id,
    store_id,
    node_id,
    sku_id,
)
~~~

Demand, inventory, covariates, model output, and decisions retain these identities. This provides several practical properties:

- Equal local store identifiers in different business units do not overwrite each other.
- A store can retain separate records after changing node.
- A store forecast can be mapped explicitly into node replenishment demand.
- A decision records both the demand source and the fulfillment location.

<code>RetailDataHandler</code> checks that demand, inventory, and covariates use coherent item keys, then creates <code>StoreNodeBinding</code> records from valid data.

## From Store Forecast to Node Replenishment

Every forecast should state whether it describes a store or a node:

~~~mermaid
flowchart LR
    A[Store SKU forecast] --> B[Read store-node mapping]
    B --> C[Allocate by routing rule]
    C --> D[Aggregate node demand]
    D --> E[Combine with node inventory]
    E --> F[Create node replenishment decision]
~~~

The current sample uses <code>forecast_scope = store</code> and synthetic one-store-to-one-node data, so it does not implement allocation shares. A customer implementation with shared nodes or dynamic routing needs allocation and aggregation before node replenishment.

## Practical Data Rules

1. Record sales and demand primarily against stores.
2. Record physical stock, inbound stock, reservations, and backorders against nodes.
3. Store the store-to-node mapping separately and give it effective dates.
4. Make every replenishment action name its target node.
5. Calculate store policies and node policies separately.
6. Retain the business unit before aggregation so local identifiers cannot collide.

## Related Implementation

- [Object and item-key definitions](../../src/ird/schema.py)
- [Data validation and store-node mapping](../../src/ird/data/handler.py)
- [Business-unit, store, and node tests](../../tests/unit/test_domain_and_data.py)
- [Architecture](../architecture.md)
- [Demand covariates and probabilistic forecasting](../demand_covariates_and_probabilistic_forecasting.md)

[Chinese version](why-stores-and-fulfillment-nodes-must-be-separated.zh-CN.md)
