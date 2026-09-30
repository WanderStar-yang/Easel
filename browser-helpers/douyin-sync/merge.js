globalThis.EaselDouyinSync = {
  normalizeText(value) {
    return String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLocaleLowerCase();
  },
  normalizeDate(value) {
    return this.normalizeText(value).replace(/[/.]/g, '-').slice(0, 16);
  },
  key(row) {
    const id = this.normalizeText(row.platform_post_id);
    if (id) return `id:${id}`;
    const title = this.normalizeText(row.title);
    const date = this.normalizeDate(row.publish_time);
    return title && date ? `composite:${date}\u0000${title}` : null;
  },
  mergeRows(existing, incoming) {
    const keyed = new Map();
    const anonymous = [];
    for (const row of [...existing, ...incoming]) {
      const key = this.key(row);
      if (!key) {
        anonymous.push(row);
        continue;
      }
      const fallback = key.startsWith('id:')
        ? this.key({ ...row, platform_post_id: null }) : null;
      if (fallback && keyed.has(fallback)) {
        const prior = keyed.get(fallback);
        keyed.delete(fallback);
        keyed.set(key, { ...prior, ...row });
      } else if (keyed.has(key)) {
        const prior = keyed.get(key);
        keyed.set(key, Object.fromEntries(Object.entries({ ...prior, ...row }).filter(([, value]) => value != null)));
      } else {
        keyed.set(key, row);
      }
    }
    return [...keyed.values(), ...anonymous];
  },
  counts(rows, observations) {
    const unique = this.mergeRows([], rows);
    const rawCount = observations ?? rows.length;
    return { rawCount, uniqueCount: unique.length, duplicateCount: Math.max(0, rawCount - unique.length) };
  },
};
