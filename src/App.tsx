import { useEffect, useState } from 'react';
import { fetchTotals } from './utils/calcTotals';
import './index.css';  // Tailwind 지시어가 들어있는 파일

type Totals = {
  a: number;
  b: number;
  done: number;
  total: number;
};

function App() {
  const [totals, setTotals] = useState<Totals | null>(null);

  // CSV 경로 (public 폴더에 두면 /data/... 로 접근)
  const CSV_PATH = '/data/2022_result.csv';

  useEffect(() => {
    const load = async () => {
      const t = await fetchTotals(CSV_PATH);
      setTotals(t);
    };

    load();                       // 첫 로드
    const id = setInterval(load, 60_000); // 1분마다 새로고침
    return () => clearInterval(id);       // 컴포넌트 언마운트 시 정리
  }, []);

  return (
    <div className="flex flex-col items-center mt-20 gap-6">
      <h1 className="text-4xl font-bold">PreCount ‒ 실시간 예측</h1>

      {totals ? (
        <>
          {/* 득표율 막대 */}
          <div className="w-80 h-8 bg-gray-200 rounded overflow-hidden relative">
            <div
              className="h-full bg-blue-500"
              style={{ width: `${totals.a}%` }}
            />
            <div
              className="h-full bg-red-500 absolute top-0 right-0"
              style={{ width: `${totals.b}%` }}
            />
          </div>
          {/* 숫자 표기 */}
          <div className="flex gap-6 text-lg">
            <span>후보A: {totals.a.toFixed(1)}%</span>
            <span>후보B: {totals.b.toFixed(1)}%</span>
          </div>
          {/* 진행률 */}
          <div className="text-sm text-gray-600">
            개표구 {totals.done}/{totals.total} ( {Math.round(
              (totals.done / totals.total) * 100,
            )}% 입력 )
          </div>
        </>
      ) : (
        <p>데이터 불러오는 중...</p>
      )}
    </div>
  );
}

export default App;
