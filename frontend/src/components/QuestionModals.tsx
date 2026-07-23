import { ImportOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Radio,
  Select,
} from "antd";
import { api } from "../api/client";

const zhihuUrlPattern = /^https:\/\/(?:www\.)?zhihu\.com\/question\/\d+(?:[/?#].*)?$/i;

export function validateZhihuUrl(value: string) {
  return zhihuUrlPattern.test(value.trim());
}

export function AddQuestionButton({ onClick }: { onClick: () => void }) {
  return (
    <Button type="primary" icon={<PlusOutlined />} onClick={onClick}>
      添加知乎问题
    </Button>
  );
}

export function AddQuestionModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: (questionId: string) => void;
}) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: api.addQuestion,
    onSuccess: async (question) => {
      await queryClient.invalidateQueries({ queryKey: ["questions"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      message.success("问题已保存到问题池");
      form.resetFields();
      onClose();
      onCreated?.(question.id);
    },
    onError: (error) => message.error(error.message),
  });
  return (
    <Modal
      title="添加知乎问题"
      open={open}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      onOk={() => form.submit()}
      confirmLoading={mutation.isPending}
      okText="保存到问题池"
      cancelText="取消"
      width={680}
      destroyOnHidden
    >
      <p className="modal-intro">
        第一阶段会保存问题，并用示例回答验证结构化观点提取。不会自动访问知乎或保存账号信息。
      </p>
      <Form
        form={form}
        layout="vertical"
        requiredMark="optional"
        initialValues={{ priority: "medium" }}
        onFinish={(values) => mutation.mutate(values)}
      >
        <Form.Item
          name="url"
          label="知乎问题链接"
          validateTrigger="onBlur"
          rules={[
            { required: true, message: "请输入知乎问题链接" },
            {
              validator: (_, value: string) =>
                !value || validateZhihuUrl(value)
                  ? Promise.resolve()
                  : Promise.reject(new Error("格式示例：https://www.zhihu.com/question/123456")),
            },
          ]}
        >
          <Input placeholder="https://www.zhihu.com/question/123456" allowClear />
        </Form.Item>
        <Form.Item
          name="title"
          label="问题标题"
          extra="建议填写，便于问题池识别；为空时会使用问题 ID 生成临时标题。"
        >
          <Input maxLength={500} showCount placeholder="例如：怎样建立稳定的学习习惯？" />
        </Form.Item>
        <Form.Item name="description" label="问题说明">
          <Input.TextArea
            rows={3}
            maxLength={10_000}
            showCount
            placeholder="补充问题背景或希望关注的角度"
          />
        </Form.Item>
        <Form.Item
          name="sample_answer"
          label="示例回答（第一阶段流程验证）"
          extra="Worker 会从这里提取观点；真实回答采集将在第二阶段实现。"
        >
          <Input.TextArea
            rows={5}
            maxLength={30_000}
            showCount
            placeholder="粘贴一段你有权使用的示例回答，或留空使用问题说明"
          />
        </Form.Item>
        <Form.Item name="priority" label="优先级">
          <Radio.Group
            options={[
              { label: "高", value: "high" },
              { label: "中", value: "medium" },
              { label: "低", value: "low" },
            ]}
            optionType="button"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export function ImportQuestionsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: api.importQuestions,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["questions"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      modal.success({
        title: "批量导入完成",
        content: `新增 ${result.created} 个，重复 ${result.duplicate} 个，失败 ${result.failed} 个。`,
      });
      form.resetFields();
      onClose();
    },
    onError: (error) => message.error(error.message),
  });

  return (
    <Modal
      title="批量导入问题"
      open={open}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      onOk={() => form.submit()}
      okText="开始导入"
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ priority: "medium" }}
        onFinish={(values: { urls: string; priority: string }) => {
          const urls = values.urls
            .split(/\r?\n/)
            .map((item) => item.trim())
            .filter(Boolean);
          mutation.mutate({ urls, priority: values.priority });
        }}
      >
        <Form.Item
          name="urls"
          label="知乎问题链接"
          extra="每行一个链接，最多 100 个；重复问题不会再次创建。"
          rules={[
            { required: true, message: "请至少输入一个链接" },
            {
              validator: (_, value: string) => {
                const invalid = (value || "")
                  .split(/\r?\n/)
                  .map((item) => item.trim())
                  .filter(Boolean)
                  .find((item) => !validateZhihuUrl(item));
                return invalid
                  ? Promise.reject(new Error(`链接格式不正确：${invalid}`))
                  : Promise.resolve();
              },
            },
          ]}
        >
          <Input.TextArea rows={9} placeholder="https://www.zhihu.com/question/123456" />
        </Form.Item>
        <Form.Item name="priority" label="统一优先级">
          <Select
            options={[
              { label: "高", value: "high" },
              { label: "中", value: "medium" },
              { label: "低", value: "low" },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export function ImportQuestionsButton({ onClick }: { onClick: () => void }) {
  return (
    <Button icon={<ImportOutlined />} onClick={onClick}>
      批量导入
    </Button>
  );
}
