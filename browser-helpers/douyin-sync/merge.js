globalThis.EaselDouyinSync = {
  key(row) {
    return row.platform_post_id || `${row.publish_time || ''}\u0000${row.title}`;
  },
  mergeRows(existing, incoming) {
    const merged = new Map(existing.map((row) => [this.key(row), row]));
    for (const row of incoming) merged.set(this.key(row), row);
    return [...merged.values()];
  },
};
