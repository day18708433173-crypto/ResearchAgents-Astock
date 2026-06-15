'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { ImageIcon, X, Loader2, AlertCircle } from 'lucide-react';
import {
  buildUserLlmHeaders,
  isUserLlmConfigComplete,
  loadUserLlmConfig,
} from '@/lib/llmConfig';

interface AttachedImage {
  id: string;
  file: File;
  previewUrl: string;
  status: 'analyzing' | 'done' | 'error';
  errorMsg?: string;
}

interface FocusTextareaProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  minRows?: number;
}

/**
 * 支持多行输入 + 图片上传的聚焦问题输入框。
 * 图片上传后调用 /api/debate/analyze-image，使用首页配置的视觉模型提取文字，
 * 追加到文本末尾。需要首页「模型接入」配置支持图片的模型（如 GPT-4o、Claude）。
 */
export default function FocusTextarea({
  value,
  onChange,
  placeholder = '输入聚焦问题或补充数据...',
  disabled = false,
  className = '',
  minRows = 2,
}: FocusTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [images, setImages] = useState<AttachedImage[]>([]);

  // 检查用户是否已在首页配置了模型（本地读取，无需网络请求）
  const userModelConfigured =
    typeof window !== 'undefined' && isUserLlmConfigComplete(loadUserLlmConfig());

  // textarea 自动高度
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const minHeight = minRows * 20 + 16;
    el.style.height = `${Math.max(minHeight, el.scrollHeight)}px`;
  }, [minRows]);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    adjustHeight();
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!userModelConfigured) return;
    const imageFiles = Array.from(e.clipboardData.items)
      .filter((item) => item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (imageFiles.length === 0) return;

    e.preventDefault(); // 阻止图片被粘贴为乱码文字
    const newImages: AttachedImage[] = imageFiles.map((file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      previewUrl: URL.createObjectURL(file),
      status: 'analyzing' as const,
    }));
    setImages((prev) => [...prev, ...newImages]);
    for (const img of newImages) void analyzeImage(img);
  };

  const analyzeImage = async (img: AttachedImage) => {
    const headers = buildUserLlmHeaders();

    try {
      const formData = new FormData();
      formData.append('file', img.file);
      const res = await fetch('/api/debate/analyze-image', {
        method: 'POST',
        headers,   // 传递 x-jh-llm-* 让后端使用用户配置的模型
        body: formData,
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || '分析失败');
      }

      const extracted: string = data.text || '';
      setImages((prev) =>
        prev.map((i) => (i.id === img.id ? { ...i, status: 'done' } : i))
      );

      if (extracted.trim()) {
        const separator = value.trim() ? '\n\n' : '';
        onChange(value + separator + `【图片数据】\n${extracted.trim()}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      setImages((prev) =>
        prev.map((i) =>
          i.id === img.id ? { ...i, status: 'error', errorMsg: msg } : i
        )
      );
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    const newImages: AttachedImage[] = files.map((file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      previewUrl: URL.createObjectURL(file),
      status: 'analyzing' as const,
    }));

    setImages((prev) => [...prev, ...newImages]);
    e.target.value = '';

    for (const img of newImages) {
      void analyzeImage(img);
    }
  };

  const removeImage = (id: string) => {
    setImages((prev) => {
      const found = prev.find((i) => i.id === id);
      if (found) URL.revokeObjectURL(found.previewUrl);
      return prev.filter((i) => i.id !== id);
    });
  };

  return (
    <div className={`relative ${className}`}>
      <div
        className={`flex items-end gap-1.5 rounded-md border border-[var(--jh-border)] bg-[var(--jh-bg)] transition-colors focus-within:border-[var(--jh-accent)] ${disabled ? 'opacity-60' : ''}`}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleTextChange}
          onPaste={handlePaste}
          placeholder={placeholder}
          disabled={disabled}
          rows={minRows}
          className="flex-1 resize-none bg-transparent px-3 py-2 text-xs text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] focus:outline-none leading-5 min-h-0"
          style={{ minHeight: `${minRows * 20 + 16}px` }}
        />

        {/* 图片上传按钮：仅当用户已配置模型时显示 */}
        {userModelConfigured && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
            title="上传图片（将使用首页配置的模型提取数据）"
            className="shrink-0 mb-1.5 mr-1.5 p-1.5 rounded text-[var(--jh-text-muted)] hover:text-[var(--jh-accent)] hover:bg-[var(--jh-bg-2)] transition-colors disabled:pointer-events-none"
          >
            <ImageIcon className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* 图片预览条 */}
      {images.length > 0 && (
        <div className="mt-1.5 space-y-1.5">
          <div className="flex flex-wrap gap-2">
            {images.map((img) => (
              <div
                key={img.id}
                className="relative group rounded-md overflow-hidden border border-[var(--jh-border)] bg-[var(--jh-bg-2)]"
                style={{ width: 56, height: 56 }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={img.previewUrl}
                  alt="附图"
                  className="w-full h-full object-cover"
                />

                {img.status === 'analyzing' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                    <Loader2 className="w-4 h-4 animate-spin text-white" />
                  </div>
                )}
                {img.status === 'error' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                    <AlertCircle className="w-4 h-4 text-red-400" />
                  </div>
                )}
                {img.status === 'done' && (
                  <div className="absolute bottom-0 inset-x-0 h-1 bg-[var(--jh-accent)]" />
                )}

                <button
                  type="button"
                  onClick={() => removeImage(img.id)}
                  className="absolute top-0.5 right-0.5 hidden group-hover:flex items-center justify-center w-4 h-4 rounded-full bg-black/70 text-white"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            ))}
          </div>

          {/* 错误信息：明显展示，不再藏在 tooltip 里 */}
          {images.filter((i) => i.status === 'error').map((img) => (
            <div
              key={`err-${img.id}`}
              className="flex items-start gap-1.5 rounded-md border border-[rgba(223,95,95,0.3)] bg-[rgba(223,95,95,0.08)] px-2.5 py-2 text-xs text-[var(--jh-danger)]"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>
                {img.errorMsg?.includes('图片分析需要配置') || img.errorMsg?.includes('请在首页') || img.errorMsg?.includes('does not support') || img.errorMsg?.includes('vision') || img.errorMsg?.includes('image') ? (
                  <>图片分析失败：当前模型不支持图片输入。请前往<strong>首页 → 模型接入</strong>，换用支持图片的模型后重试。（如 GPT-4o、Gemini 1.5 Pro、通义千问-VL、智谱 GLM-4V）</>
                ) : (
                  <>图片分析失败：{img.errorMsg || '未知错误'}</>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* 提示：模型未配置时说明如何启用图片上传 */}
      {!userModelConfigured && (
        <p className="mt-1 text-[10px] text-[var(--jh-text-muted)]">
          配置支持图片的模型（如 GPT-4o）后可上传图片
        </p>
      )}
    </div>
  );
}
