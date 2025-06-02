import Papa from 'papaparse';

export type PrecinctRow = {
  precinct_id: string;
  voters: number;
  cand1_pct: number; // 0~100
  cand2_pct: number;
};

export async function fetchTotals(path: string) {
  const res = await fetch(path);
  const txt = await res.text();
  const { data } = Papa.parse<PrecinctRow>(txt, { header: true });

  let totalV = 0, sumA = 0, sumB = 0, done = 0;

  data.forEach(r => {
    const v = Number(r.voters) || 0;
    const aPct = Number(r.cand1_pct);
    const bPct = Number(r.cand2_pct);
    if (!Number.isNaN(aPct) && !Number.isNaN(bPct)) {
      sumA += v * aPct / 100;
      sumB += v * bPct / 100;
      totalV += v;
      done += 1;
    }
  });

  return {
    a: sumA / totalV * 100,
    b: sumB / totalV * 100,
    done,
    total: data.length,
  };
}
