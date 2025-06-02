import Papa from 'papaparse';

export type PrecinctRow = {
  precinct_id: string;
  voters: number;
  cand1_pct: string;
  cand2_pct: string;
};

export async function fetchTotals(path: string) {
  const res = await fetch(path);
  const text = await res.text();
  const { data } = Papa.parse<PrecinctRow>(text, { header: true });

  let votersSum = 0, candASum = 0, candBSum = 0, done = 0;

  data.forEach(r => {
    const v = Number(r.voters);
    const a = Number(r.cand1_pct);
    const b = Number(r.cand2_pct);
    if (!isNaN(a) && !isNaN(b)) {
      votersSum += v;
      candASum += (v * a) / 100;
      candBSum += (v * b) / 100;
      done += 1;
    }
  });

  return {
    a: (candASum / votersSum) * 100,
    b: (candBSum / votersSum) * 100,
    done,
    total: data.length,
  };
}
