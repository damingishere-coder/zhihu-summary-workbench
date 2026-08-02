import { Progress } from "antd";

export function ProgressCell({ progress }: { progress: number }) {
  return (
    <div className="progress-cell" aria-label={`任务进度 ${progress}%`}>
      <span>{progress}%</span>
      <Progress
        percent={progress}
        showInfo={false}
        size="small"
        status={progress === 100 ? "success" : "active"}
      />
    </div>
  );
}

