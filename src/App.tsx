import { useEffect, useState } from 'react';
import { fetchTotals } from './utils/calcTotals';
import './index.css';

type Totals = { a: number; b: number; done: number; total: number };

export default function App() {
  const [tot, setTot] = useState<Totals | null>(null);

  useEffect(() => {
    const load = async () => setTot(await fetchTotals('/data/2022_result.csv'));
    load();                            // 최초
    const id = setInterval(load, 60_000); // 1분 주기
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col items-center mt-20 gap-6">
      <h1 className="text-4xl font-bold">PreCount LIVE</h1>

      {tot ? (
        <>
          {/* 득표율 막대 */}
          <div className="w-80 h-8 bg-gray-200 rounded overflow-hidden relative">
            <div className="h-full bg-blue-500" style={{ width: `${tot.a}%` }} />
            <div className="h-full bg-red-500 absolute top-0 right-0" style={{ width: `${tot.b}%` }} />
          </div>

          <div className="flex gap-6 text-lg">
            <span>후보 A: {tot.a.toFixed(1)}%</span>
            <span>후보 B: {tot.b.toFixed(1)}%</span>
          </div>

          <div className="text-sm text-gray-600">
            개표구 {tot.done}/{tot.total} (
            {Math.round((tot.done / tot.total) * 100)}% 입력)
          </div>
        </>
      ) : (
        <p>데이터 불러오는 중…</p>
      )}
    </div>
  );
}
