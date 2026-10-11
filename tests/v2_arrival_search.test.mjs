import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { rankPois, searchPlaces } from "../backend/src/campuspilot/web_assets/v2/places.mjs";

const ours = [{ place_id: "lib", name: "东区图书馆", aliases: ["成都理工大学东区图书馆"] }, { place_id: "x", name: "东区图书馆报告厅" }];
test("map search: our places first, exact before prefix, transit POIs dropped", () => {
  const local = searchPlaces(ours, "东区图书馆");
  assert.deepEqual(local.map((p) => p.place_id), ["lib", "x"]);
  const pois = [
    { name: "东区图书馆(公交站)", type: "交通设施服务;公交车站" },
    { name: "东区图书馆地铁站" },
    { name: "成都理工大学东区图书馆" },
    { name: "东区图书馆旁快递驿站" },
    { name: "东区图书馆", type: "科教文化服务" },
    { name: "图书馆停车场" },
    { name: "某某站", type: "交通设施服务;公交车站" },
  ];
  assert.deepEqual(rankPois(pois, local, "东区图书馆").map((p) => p.name), ["东区图书馆旁快递驿站"]);
  assert.deepEqual(rankPois([{ name: "其它东区图书馆" }, { name: "西区图书馆" }, { name: "西区图书馆A" }], [], "西区图书馆").map((p) => p.name), ["西区图书馆", "西区图书馆A", "其它东区图书馆"]);
});
test("arrival: dedicated card with 已到达 + 完成, shown while guiding", () => {
  const main = readFileSync(new URL("../backend/src/campuspilot/web_assets/v2/main.mjs", import.meta.url), "utf8");
  const css = readFileSync(new URL("../backend/src/campuspilot/web_assets/v2/app.css", import.meta.url), "utf8");
  assert.match(main, /onArrive: \(\) => \{ if \(guideTarget\) showArrival\(guideTarget\); \}/);
  assert.match(main, /"已到达"/); assert.match(main, /finishArrival \}, "完成"/);
  assert.match(css, /body\.guiding \.place-card:not\(\.arrival\)\{display:none\}/);
});
