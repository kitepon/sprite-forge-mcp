const key = "sprite-forge.records.v1";

export const state = {
  activeJob: null,
  records: JSON.parse(localStorage.getItem(key) || "[]"),
  events: [],
  save(record) {
    this.records = [record, ...this.records.filter((item) => item.id !== record.id)].slice(0, 30);
    localStorage.setItem(key, JSON.stringify(this.records));
  },
};
