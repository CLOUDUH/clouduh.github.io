'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  Check,
  FileJson,
  FolderInput,
  FolderOpen,
  ImageOff,
  Search,
  SkipForward,
  Upload,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

type Item = {
  id: string;
  relativePath: string;
  filename: string;
  currentFolder: string;
  captureDate: string | null;
  dateSource: string;
  fileCreateDate: string | null;
  fileModifyDate: string | null;
  expectedStart: string;
  expectedEnd: string;
  suggestedFolder: string;
  reason: string;
  thumbnail: string | null;
};

type Manifest = {
  version: number;
  generatedAt: string;
  range: string;
  ignoredFolders: string[];
  folderCount: number;
  scanned: number;
  cameraFilesFixed: number;
  count: number;
  folders: string[];
  items: Item[];
};

type Decision = 'unset' | 'keep' | 'apply' | 'skip';
type Review = {
  decision: Decision;
  correctedDate: string;
  timeText: string;
  targetFolder: string;
  notes: string;
  updatedAt: string;
};

const STORAGE_KEY = 'photo-range-review-2022-export-v5';
const EMPTY: Review = { decision: 'unset', correctedDate: '', timeText: '', targetFolder: '', notes: '', updatedAt: '' };

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function RangeReviewPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [folder, setFolder] = useState('all');
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState('');
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch(`/range-review/review-items.json?v=${Date.now()}`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('无法读取跨文件夹审核清单');
        return response.json();
      })
      .then(setManifest)
      .catch((reason) => setError(reason instanceof Error ? reason.message : '加载失败'));
    try {
      setReviews(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}'));
    } catch {
      setReviews({});
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews));
  }, [reviews]);

  function isComplete(item: Item) {
    const saved = reviews[item.id];
    if (!saved) return false;
    if (saved.decision === 'keep' || saved.decision === 'skip') return true;
    const hasTimeConclusion = Boolean(saved.timeText?.trim() || saved.correctedDate?.trim());
    return saved.decision === 'apply' && Boolean(saved.targetFolder) && hasTimeConclusion;
  }

  const items = useMemo(() => {
    const value = query.trim().toLowerCase();
    return (manifest?.items ?? []).filter((item) => {
      const complete = isComplete(item);
      const matchesFolder = folder === 'all' || item.currentFolder === folder;
      const matchesStatus = status === 'all' || (status === 'pending' ? !complete : complete);
      const matchesQuery = !value || `${item.filename} ${item.relativePath} ${item.suggestedFolder}`.toLowerCase().includes(value);
      return matchesFolder && matchesStatus && matchesQuery;
    });
  }, [manifest, reviews, folder, status, query]);

  useEffect(() => setActiveIndex(0), [folder, status, query]);

  const active = items[Math.min(activeIndex, Math.max(0, items.length - 1))];
  const review = active ? reviews[active.id] ?? EMPTY : EMPTY;
  const chosenFolder = active ? review.targetFolder || active.currentFolder : '';
  const reviewedCount = manifest?.items.filter((item) => isComplete(item)).length ?? 0;

  function update(patch: Partial<Review>) {
    if (!active) return;
    setReviews((current) => ({
      ...current,
      [active.id]: {
        ...(current[active.id] ?? EMPTY),
        ...patch,
        updatedAt: new Date().toISOString(),
      },
    }));
  }

  function move(step: number) {
    setActiveIndex((value) => Math.max(0, Math.min(items.length - 1, value + step)));
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input,textarea,select,[role="combobox"]')) return;
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        move(-1);
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        move(1);
      }
      if (event.key.toLowerCase() === 'k' && active) {
        update({ decision: 'keep', targetFolder: active.currentFolder, correctedDate: '' });
      }
      if (event.key.toLowerCase() === 'm' && active) {
        update({ decision: 'apply', targetFolder: chosenFolder });
      }
      if (event.key.toLowerCase() === 's') update({ decision: 'skip' });
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  function exportJson() {
    if (!manifest) return;
    download(
      'photo-range-review.json',
      JSON.stringify(
        {
          version: 1,
          exportedAt: new Date().toISOString(),
          sourceGeneratedAt: manifest.generatedAt,
          range: manifest.range,
          total: manifest.count,
          reviewed: reviewedCount,
          reviews: manifest.items.map((item) => ({
            id: item.id,
            relativePath: item.relativePath,
            currentFolder: item.currentFolder,
            currentCapture: item.captureDate,
            suggestedFolder: item.suggestedFolder,
            ...(reviews[item.id] ?? EMPTY),
            timeText: reviews[item.id]?.timeText ?? reviews[item.id]?.correctedDate ?? '',
          })),
        },
        null,
        2,
      ),
    );
  }

  async function importJson(file?: File) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const next: Record<string, Review> = {};
      for (const row of data.reviews ?? []) {
        if (!row.id) continue;
        next[row.id] = {
          decision: row.decision ?? 'unset',
          correctedDate: row.correctedDate ?? '',
          timeText: row.timeText ?? row.correctedDate ?? '',
          targetFolder: row.targetFolder ?? '',
          notes: row.notes ?? '',
          updatedAt: row.updatedAt ?? '',
        };
      }
      setReviews(next);
    } catch {
      window.alert('无法导入该文件。');
    }
  }

  if (error) return <main className="grid min-h-screen place-items-center p-8 text-destructive">{error}</main>;
  if (!manifest) return <main className="min-h-screen animate-pulse bg-background" />;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b bg-card/94 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1680px] items-center gap-4 px-4 py-3 lg:px-8">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <FolderInput className="size-5 text-primary" />
              <h1 className="font-semibold">2022 导出时间审核</h1>
              <Badge variant="outline">本机私密</Badge>
              <Badge variant="secondary">本轮自动修正 {manifest.cameraFilesFixed} 张</Badge>
              <a href="/calibrate" className="text-xs text-muted-foreground hover:text-foreground">日期校准台</a>
            </div>
            <Progress value={manifest.count ? (reviewedCount / manifest.count) * 100 : 0} className="mt-2 max-w-xl">
              <ProgressLabel>已确认</ProgressLabel>
              <ProgressValue>{reviewedCount}/{manifest.count}</ProgressValue>
            </Progress>
          </div>
          <div className="hidden gap-2 sm:flex">
            <Button variant="outline" onClick={() => importRef.current?.click()}><Upload />导入</Button>
            <Button onClick={exportJson}><FileJson />导出结果</Button>
          </div>
          <input ref={importRef} type="file" accept="application/json" className="hidden" onChange={(event) => importJson(event.target.files?.[0])} />
        </div>
      </header>

      <div className="mx-auto max-w-[1680px] p-4 lg:p-8">
        <div className="mb-4 flex flex-wrap gap-2">
          <Select value={folder} onValueChange={(value) => setFolder(value ?? 'all')}>
            <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部异常文件夹</SelectItem>
              {[...new Set(manifest.items.map((item) => item.currentFolder))].sort().map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={(value) => setStatus(value ?? 'all')}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="pending">仅待处理</SelectItem>
              <SelectItem value="reviewed">仅已处理</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative min-w-64 flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名或目标文件夹" />
          </div>
          <Badge variant="secondary">{items.length} 张</Badge>
        </div>

        {active ? (
          <div className="grid overflow-hidden rounded-3xl border bg-card shadow-sm lg:grid-cols-[minmax(0,1.25fr)_520px]">
            <section className="relative grid min-h-[60vh] place-items-center bg-photo-stage p-4 lg:min-h-[75vh]">
              {active.thumbnail ? (
                <img src={active.thumbnail} alt={active.filename} className="max-h-[72vh] max-w-full object-contain shadow-2xl" />
              ) : (
                <div className="text-center text-stone-400"><ImageOff className="mx-auto mb-2" />无缩略图</div>
              )}
              <Badge className="absolute left-4 top-4 bg-black/65 text-white">{activeIndex + 1}/{items.length}</Badge>
            </section>

            <aside className="flex flex-col p-5">
              <p className="text-xs font-medium uppercase tracking-[.12em] text-muted-foreground">当前：{active.currentFolder}</p>
              <h2 className="mt-1 break-all text-lg font-semibold">{active.filename}</h2>
              <p className="mt-1 break-all text-xs text-muted-foreground">{active.relativePath}</p>

              <div className="mt-4 space-y-2 rounded-2xl border bg-muted/35 p-3 text-xs">
                <div><span className="text-muted-foreground">拍摄时间：</span><span className="font-mono">{active.captureDate ?? '无'}</span></div>
                <div><span className="text-muted-foreground">日期来源：</span>{active.dateSource}</div>
                <div><span className="text-muted-foreground">当前范围：</span>{active.expectedStart} 至 {active.expectedEnd}</div>
                <div><span className="text-muted-foreground">系统建议：</span><span className="font-medium text-primary">{active.suggestedFolder}</span></div>
              </div>

              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="text-sm font-medium">点击应该所属的文件夹</label>
                  <Badge variant="outline">已选：{chosenFolder}</Badge>
                </div>
                <div className="flex flex-wrap content-start gap-1 rounded-2xl border bg-muted/25 p-2.5">
                  {manifest.folders.map((value) => (
                    <Button
                      key={value}
                      type="button"
                      variant={chosenFolder === value ? 'default' : value === active.currentFolder ? 'secondary' : 'outline'}
                      className="h-6 rounded-full px-2 text-[10px] leading-none"
                      onClick={() => update({ targetFolder: value, decision: 'apply' })}
                    >
                      {value}
                    </Button>
                  ))}
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">绿色为当前选择；浅色为照片现在所在的文件夹。标签只保存选择，不会立即移动原文件。</p>
              </div>

              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="text-sm font-medium">时间修正说明</label>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline-offset-4 hover:underline"
                    onClick={() => update({ timeText: '当前拍摄时间正确', decision: 'apply' })}
                  >
                    当前时间正确
                  </button>
                </div>
                <Textarea
                  className="min-h-20"
                  value={review.timeText ?? ''}
                  onChange={(event) => update({ timeText: event.target.value, decision: 'apply' })}
                  placeholder="不用按格式写。例如：2019年11月比赛后；应该是春节前两天晚上；和上一张同一时间；只知道是2020年暑假……"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">可以随意描述，我会结合相邻照片、文件名和你的说明统一解析。</p>
              </div>

              <div className="mt-4">
                <label className="mb-2 block text-sm font-medium">其他备注或照片关联</label>
                <Textarea className="min-h-20" value={review.notes} onChange={(event) => update({ notes: event.target.value })} placeholder="例如：和后一张是同一组、另一张画质更好、人物或事件线索……" />
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                <Button variant={review.decision === 'keep' ? 'default' : 'outline'} onClick={() => update({ decision: 'keep', targetFolder: active.currentFolder, correctedDate: '', timeText: '当前拍摄时间正确' })}><Check />保持当前</Button>
                <Button variant={review.decision === 'apply' ? 'default' : 'outline'} onClick={() => update({ decision: 'apply', targetFolder: chosenFolder })}><CalendarClock />确认修正</Button>
                <Button variant={review.decision === 'skip' ? 'secondary' : 'outline'} onClick={() => update({ decision: 'skip' })}><SkipForward />稍后处理</Button>
              </div>

              <div className="mt-auto pt-6">
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" disabled={activeIndex === 0} onClick={() => move(-1)}><ArrowLeft />上一张</Button>
                  <Button disabled={activeIndex >= items.length - 1} onClick={() => move(1)}>下一张<ArrowRight /></Button>
                </div>
                <p className="mt-3 text-center text-[11px] text-muted-foreground">快捷键：← → 切换 · K 保持 · M 确认修正 · S 跳过</p>
              </div>
            </aside>
          </div>
        ) : (
          <div className="grid min-h-72 place-items-center rounded-3xl border border-dashed">
            <div className="text-center"><FolderOpen className="mx-auto mb-2 text-muted-foreground" /><p>当前筛选没有照片</p></div>
          </div>
        )}
      </div>
    </main>
  );
}
