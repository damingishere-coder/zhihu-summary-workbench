import { CalendarOutlined, CheckCircleOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Calendar,
  Input,
  Modal,
  Radio,
  Space,
  Table,
  Tabs,
  Tag,
} from "antd";
import type { Dayjs } from "dayjs";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { SectionNav } from "../components/SectionNav";
import { useListLocation } from "../hooks/useListLocation";
import { allDrafts } from "../api/collections";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Draft, PublishReadiness, PublishSchedule } from "../types";
import { formatDateTime } from "../utils/format";

type ReadyRow = Draft & { readiness: PublishReadiness };

function localDateTimeTomorrow() {
  const value = new Date(Date.now() + 24 * 60 * 60 * 1000);
  value.setMinutes(0, 0, 0);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

export function PublishPage() {
  const { message } = App.useApp();
  const list = useListLocation();
  const queryClient = useQueryClient();
  const [scheduleDraft, setScheduleDraft] = useState<ReadyRow | null>(null);
  const [scheduledFor, setScheduledFor] = useState(localDateTimeTomorrow);
  const [mode, setMode] = useState<"manual" | "assisted">("manual");
  const [executeSchedule, setExecuteSchedule] =
    useState<PublishSchedule | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const readiness = useQuery({
    queryKey: ["drafts", "publish-readiness"],
    queryFn: async () => {
      const drafts = await allDrafts();
      const rows = await Promise.all(
        drafts.items.map(async (draft) => ({
          ...draft,
          readiness: await api.publishReadiness(draft.id),
        })),
      );
      return rows;
    },
  });
  const schedules = useQuery({
    queryKey: ["publish-schedules"],
    queryFn: api.publishSchedules,
  });
  const records = useQuery({
    queryKey: ["publish-records"],
    queryFn: api.publishRecords,
  });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["publish-schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["publish-records"] }),
      queryClient.invalidateQueries({
        queryKey: ["drafts", "publish-readiness"],
      }),
      queryClient.invalidateQueries({ queryKey: ["daily-plan"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };
  const create = useMutation({
    mutationFn: () =>
      api.createPublishSchedule({
        article_draft_id: scheduleDraft!.id,
        scheduled_for: new Date(scheduledFor).toISOString(),
        mode,
      }),
    onSuccess: async () => {
      message.success("排期已创建，并冻结当前文章和图片版本");
      setScheduleDraft(null);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const reschedule = useMutation({
    mutationFn: ({ item, day }: { item: PublishSchedule; day: Dayjs }) => {
      const previous = new Date(item.scheduled_for);
      const target = day
        .hour(previous.getHours())
        .minute(previous.getMinutes())
        .second(0);
      return api.updatePublishSchedule(item.id, {
        scheduled_for: target.toISOString(),
      });
    },
    onSuccess: async () => {
      message.success("排期已移动");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const execute = useMutation({
    mutationFn: () =>
      api.executePublishSchedule(executeSchedule!.id, confirmation),
    onSuccess: async (record) => {
      message.success(
        record.status === "paused"
          ? "已安全暂停并记录原因"
          : "发布包已准备，等待人工操作",
      );
      setExecuteSchedule(null);
      setConfirmation("");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const schedulesByDay = useMemo(() => {
    const groups = new Map<string, PublishSchedule[]>();
    schedules.data?.forEach((item) => {
      const key = new Date(item.scheduled_for).toLocaleDateString("zh-CN");
      groups.set(key, [...(groups.get(key) ?? []), item]);
    });
    return groups;
  }, [schedules.data]);

  const contentColumns = [
    {
      title: "内容",
      dataIndex: "title",
      key: "title",
      ellipsis: false,
      render: (value: string, row: ReadyRow) => (
        <div className="table-title">
          <Link
            to={`/drafts/${row.id}/review?step=review&returnTo=${encodeURIComponent("/publish?" + new URLSearchParams({ tab: list.get("tab", "content"), page: String(list.page) }))}`}
          >
            {value}
          </Link>
          <small>{row.question_title}</small>
          <div className="publish-version-summary">
            <Tag>
              {row.readiness.article_approved
                ? `文章已审核 v${row.readiness.article_version}`
                : "文章待审核"}
            </Tag>
            <Tag>
              {row.readiness.image_rendered
                ? `配图已渲染 v${row.readiness.image_version}`
                : "配图待渲染"}
            </Tag>
          </div>
        </div>
      ),
    },
    {
      title: "准备状态",
      key: "ready",
      width: 200,
      render: (_: unknown, row: ReadyRow) =>
        row.readiness.ready ? (
          <Tag color="success" icon={<CheckCircleOutlined />}>
            可以导出
          </Tag>
        ) : (
          <span className="publish-blocker">
            {row.readiness.blockers.join("；")}
          </span>
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 160,
      render: (_: unknown, row: ReadyRow) => (
        <Space wrap>
          <Button
            type="primary"
            size="small"
            disabled={!row.readiness.ready}
            href={
              row.readiness.ready ? api.publishPackageUrl(row.id) : undefined
            }
          >
            下载发布包
          </Button>
          <Button
            size="small"
            disabled={!row.readiness.ready}
            onClick={() => setScheduleDraft(row)}
          >
            加入排期
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="导出与发布"
        description="检查图文准备状态，下载后在知乎完成发布。"
      />
      <SectionNav section="works" />
      <section className="work-surface publish-workspace">
        <Tabs
          activeKey={
            ["content", "calendar", "records"].includes(list.get("tab"))
              ? list.get("tab")
              : "content"
          }
          onChange={(value) => list.set("tab", value)}
          items={[
            {
              key: "content",
              label: "导出准备",
              children: readiness.isLoading ? (
                <LoadingBlock rows={8} />
              ) : readiness.isError ? (
                <ErrorState
                  error={readiness.error}
                  onRetry={() => void readiness.refetch()}
                />
              ) : (
                <Table<ReadyRow>
                  rowKey="id"
                  columns={contentColumns}
                  dataSource={readiness.data}
                  pagination={{
                    current: list.page,
                    onChange: (page) => list.set("page", page),
                    showSizeChanger: false,
                    pageSize: 10,
                    hideOnSinglePage: true,
                  }}
                  locale={{ emptyText: "暂无草稿" }}
                />
              ),
            },
            {
              key: "calendar",
              label: (
                <>
                  <CalendarOutlined /> 发布日历
                </>
              ),
              children: schedules.isLoading ? (
                <LoadingBlock rows={5} />
              ) : schedules.isError ? (
                <ErrorState
                  error={schedules.error}
                  onRetry={() => void schedules.refetch()}
                />
              ) : (
                <Calendar
                  className="publish-calendar"
                  cellRender={(day) => {
                    const items =
                      schedulesByDay.get(
                        day.toDate().toLocaleDateString("zh-CN"),
                      ) ?? [];
                    return (
                      <div
                        className="publish-calendar-cell"
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                          const id =
                            event.dataTransfer.getData("text/schedule-id");
                          const item = schedules.data?.find(
                            (value) => value.id === id,
                          );
                          if (item) reschedule.mutate({ item, day });
                        }}
                      >
                        {items.map((item) => (
                          <button
                            type="button"
                            key={item.id}
                            className="publish-calendar-item"
                            draggable
                            onDragStart={(event) =>
                              event.dataTransfer.setData(
                                "text/schedule-id",
                                item.id,
                              )
                            }
                            onClick={() => setExecuteSchedule(item)}
                          >
                            <span>
                              {new Date(item.scheduled_for).toLocaleTimeString(
                                "zh-CN",
                                { hour: "2-digit", minute: "2-digit" },
                              )}
                            </span>
                            <b>{item.article_title}</b>
                            <StatusTag status={item.status} />
                          </button>
                        ))}
                      </div>
                    );
                  }}
                />
              ),
            },
            {
              key: "records",
              label: `发布记录 ${records.data?.length ?? 0}`,
              children: records.isLoading ? (
                <LoadingBlock rows={5} />
              ) : records.isError ? (
                <ErrorState
                  error={records.error}
                  onRetry={() => void records.refetch()}
                />
              ) : (
                <Table
                  rowKey="id"
                  dataSource={records.data}
                  columns={[
                    {
                      title: "时间",
                      dataIndex: "created_at",
                      width: 160,
                      render: (value: string) => formatDateTime(value, true),
                    },
                    {
                      title: "状态",
                      dataIndex: "status",
                      width: 180,
                      render: (value: string) => <StatusTag status={value} />,
                    },
                    {
                      title: "文章版本",
                      dataIndex: "article_version_id",
                      ellipsis: true,
                    },
                    {
                      title: "图片版本",
                      dataIndex: "image_version_id",
                      ellipsis: true,
                    },
                    {
                      title: "错误/暂停原因",
                      dataIndex: "error_message",
                      render: (value: string | null) => value || "—",
                    },
                  ]}
                  pagination={{
                    current: list.page,
                    onChange: (page) => list.set("page", page),
                    showSizeChanger: false,
                    pageSize: 10,
                    hideOnSinglePage: true,
                  }}
                  locale={{ emptyText: "暂无发布记录" }}
                />
              ),
            },
          ]}
        />
      </section>

      <Modal
        title="创建发布排期"
        open={Boolean(scheduleDraft)}
        okText="冻结版本并排期"
        confirmLoading={create.isPending}
        onOk={() => create.mutate()}
        onCancel={() => setScheduleDraft(null)}
      >
        <p>
          <strong>{scheduleDraft?.title}</strong>
        </p>
        <label className="modal-field-label" htmlFor="publish-time">
          发布时间
        </label>
        <Input
          id="publish-time"
          type="datetime-local"
          value={scheduledFor}
          onChange={(event) => setScheduledFor(event.target.value)}
        />
        <label className="modal-field-label">发布模式</label>
        <Radio.Group
          value={mode}
          onChange={(event) => setMode(event.target.value)}
        >
          <Radio value="manual">人工发布包（推荐）</Radio>
          <Radio value="assisted">浏览器辅助（仍需人工复核）</Radio>
        </Radio.Group>
      </Modal>

      <Modal
        title="发布前最终确认"
        open={Boolean(executeSchedule)}
        okText="确认并准备发布"
        okButtonProps={{ disabled: confirmation !== "确认发布" }}
        confirmLoading={execute.isPending}
        onOk={() => execute.mutate()}
        onCancel={() => {
          setExecuteSchedule(null);
          setConfirmation("");
        }}
      >
        <Alert
          type="warning"
          showIcon
          title="这是有外部影响的操作"
          description="系统已冻结文章与图片版本。请输入“确认发布”；辅助模式仍会在登录、验证码或风控处暂停。"
        />
        <label className="modal-field-label" htmlFor="publish-confirmation">
          确认文字
        </label>
        <Input
          id="publish-confirmation"
          value={confirmation}
          placeholder="确认发布"
          onChange={(event) => setConfirmation(event.target.value)}
        />
        {executeSchedule && (
          <Space className="publish-frozen-versions" wrap>
            <Tag>文章 v{executeSchedule.article_version ?? "—"}</Tag>
            <Tag>图片 v{executeSchedule.image_version ?? "—"}</Tag>
            <Tag>
              {executeSchedule.mode === "manual" ? "人工模式" : "浏览器辅助"}
            </Tag>
          </Space>
        )}
      </Modal>
    </div>
  );
}
