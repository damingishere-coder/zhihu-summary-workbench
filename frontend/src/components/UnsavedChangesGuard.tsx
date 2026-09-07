import { Button, Modal, Space } from "antd";
import { useCallback, useState } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";

export function UnsavedChangesGuard({
  dirty,
  busy,
  onSave,
}: {
  dirty: boolean;
  busy: boolean;
  onSave?: () => Promise<unknown>;
}) {
  const [saving, setSaving] = useState(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      (dirty || busy) && currentLocation.pathname !== nextLocation.pathname,
  );
  useBeforeUnload(
    useCallback(
      (event) => {
        if (dirty || busy) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [dirty, busy],
    ),
  );
  return (
    <Modal
      title={busy ? "正在处理这篇作品" : "还有未保存的修改"}
      open={blocker.state === "blocked"}
      onCancel={() => !saving && blocker.state === "blocked" && blocker.reset()}
      footer={
        <Space wrap>
          <Button
            disabled={saving}
            onClick={() => blocker.state === "blocked" && blocker.reset()}
          >
            留在这里
          </Button>
          <Button
            danger
            disabled={busy || saving}
            onClick={() => blocker.state === "blocked" && blocker.proceed()}
          >
            放弃修改并离开
          </Button>
          {onSave && (
            <Button
              type="primary"
              loading={saving}
              disabled={busy}
              onClick={async () => {
                setSaving(true);
                try {
                  await onSave();
                  if (blocker.state === "blocked") blocker.proceed();
                } catch {
                  /* The mutation reports the error and preserves the input. */
                } finally {
                  setSaving(false);
                }
              }}
            >
              保存并离开
            </Button>
          )}
        </Space>
      }
    >
      <p>
        {busy
          ? "请等待当前操作结束，避免丢失结果。"
          : "离开会丢失尚未保存的文章或配图修改。"}
      </p>
    </Modal>
  );
}
