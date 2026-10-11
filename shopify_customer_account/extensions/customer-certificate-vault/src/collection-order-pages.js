// Customer Account API only: no caller-supplied customer identity or admin lookup.
export async function loadCollectionOrders(fetchPage, apiVersion, query) {
  const orders = [];
  const cursors = new Set();
  const orderIds = new Set();
  let after = null;
  let owner = null;
  for (let page = 0; page < 20; page += 1) {
    const response = await fetchPage(`shopify://customer-account/api/${apiVersion}/graphql.json`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query, variables: {after}}),
    });
    const payload = await response.json();
    if (!response.ok) throw Object.assign(new Error("Customer Account API request failed."), {status: response.status});
    if (Array.isArray(payload.errors) && payload.errors.length) {
      throw Object.assign(new Error("Customer Account API query failed."), {graphQLErrors: payload.errors});
    }
    const customer = payload.data?.customer;
    if (!customer?.id || (owner && customer.id !== owner.id)) {
      throw Object.assign(new Error("Customer session changed. Refresh and sign in again."), {status: 401});
    }
    owner = customer;
    const connection = customer.orders;
    if (!Array.isArray(connection?.nodes) || typeof connection.pageInfo?.hasNextPage !== "boolean") {
      throw new Error("Collection order history is incomplete. Please retry.");
    }
    for (const order of connection.nodes) {
      if (!order?.id || orderIds.has(order.id)) throw new Error("Collection order history changed. Please retry.");
      orderIds.add(order.id);
      orders.push(order);
    }
    if (!connection.pageInfo.hasNextPage) return {customer: {id: owner.id}, orders};
    const cursor = connection.pageInfo.endCursor;
    if (!cursor || cursors.has(cursor)) throw new Error("Collection order pagination is incomplete. Please retry.");
    cursors.add(cursor);
    after = cursor;
  }
  throw new Error("Collection order history exceeds the verification limit. Contact Sports Cave for assistance.");
}
