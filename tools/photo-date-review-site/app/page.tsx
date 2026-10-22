'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, CalendarDays, Check, Download, Eye, FileJson, FolderOpen, ImageOff, RotateCcw, Search, Upload, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

type Candidate = { relativePath: string; thumbnail: string | null; score: number; phashDistance: number };
type ReviewItem = { id: string; relativePath: string; filename: string; event: string; kind: string; classification: string; currentCapture: string; suggestedMonth: string; thumbnail: string | null; candidates: Candidate[] };
type Manifest = { version: number; generatedAt: string; count: number; items: ReviewItem[] };
type Decision = 'unset' | 'keep' | 'set' | 'skip';
type Precision = 'month' | 'day' | 'exact';
type Review = { decision: Decision; precision: Precision; month: string; date: string; time: string; notes: string; updatedAt: string };

const STORAGE_KEY = 'photo-date-review-v1';
const emptyReview: Review = { decision: 'unset', precision: 'month', month: '', date: '', time: '', notes: '', updatedAt: '' };

function classificationLabel(value: string) {
  const labels: Record<string, string> = {
    no_source_images: '没有可比较原片',
    weak_visual_match: '存在弱匹配候选',
    root_decode_failed: '缩略图读取失败',
    source_decode_failed: '候选原片读取失败',
  };
  return labels[value] ?? value;
}

function downloadFile(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown) { return `"${String(value ?? '').replaceAll('"', '""')}"`; }

export default function Home() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [activeId, setActiveId] = useState('');
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [loadError, setLoadError] = useState('');
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const monthRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/review/review-items.json')
      .then((response) => { if (!response.ok) throw new Error('无法读取照片清单'); return response.json(); })
      .then((data: Manifest) => { setManifest(data); setActiveId(data.items[0]?.id ?? ''); })
      .catch((error) => setLoadError(error instanceof Error ? error.message : '加载失败'));
    try { const saved = localStorage.getItem(STORAGE_KEY); if (saved) setReviews(JSON.parse(saved)); } catch { /* Ignore a corrupt local draft. */ }
  }, []);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews)); }, [reviews]);

  const items = useMemo(() => {
    if (!manifest) return [];
    return manifest.items.filter((item) => {
      const review = reviews[item.id] ?? emptyReview;
      const filterMatch = filter === 'all' || (filter === 'pending' && review.decision === 'unset') || (filter === 'reviewed' && review.decision !== 'unset') || review.decision === filter || item.classification === filter;
      return filterMatch && `${item.event} ${item.filename} ${item.relativePath}`.toLowerCase().includes(query.trim().toLowerCase());
    });
  }, [manifest, reviews, filter, query]);

  useEffect(() => { if (items.length && !items.some((item) => item.id === activeId)) setActiveId(items[0].id); }, [items, activeId]);

  const activeIndex = Math.max(0, items.findIndex((item) => item.id === activeId));
  const active = items[activeIndex];
  const review = active ? reviews[active.id] ?? emptyReview : emptyReview;
  const reviewedCount = manifest ? manifest.items.filter((item) => (reviews[item.id]?.decision ?? 'unset') !== 'unset').length : 0;

  function updateReview(patch: Partial<Review>) {
    if (!active) return;
    setReviews((current) => ({ ...current, [active.id]: { ...(current[active.id] ?? emptyReview), ...patch, updatedAt: new Date().toISOString() } }));
  }

  function move(step: number) {
    if (!items.length) return;
    const next = Math.min(items.length - 1, Math.max(0, activeIndex + step));
    setActiveId(items[next].id);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input, textarea, [role="combobox"]')) return;
      if (event.key === 'ArrowLeft') move(-1);
      if (event.key === 'ArrowRight') move(1);
      if (event.key.toLowerCase() === 'k') updateReview({ decision: 'keep' });
      if (event.key.toLowerCase() === 's') updateReview({ decision: 'skip' });
      if (event.key.toLowerCase() === 'd') { updateReview({ decision: 'set' }); monthRef.current?.focus(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  function exportJson() {
    if (!manifest) return;
    const payload = { version: 1, exportedAt: new Date().toISOString(), sourceGeneratedAt: manifest.generatedAt, total: manifest.count, reviewed: reviewedCount, reviews: manifest.items.map((item) => ({ id: item.id, relativePath: item.relativePath, event: item.event, filename: item.filename, currentCapture: item.currentCapture, ...(reviews[item.id] ?? emptyReview) })) };
    downloadFile('photo-date-review.json', JSON.stringify(payload, null, 2), 'application/json');
  }

  function exportCsv() {
    if (!manifest) return;
    const columns = ['relativePath', 'event', 'filename', 'currentCapture', 'decision', 'precision', 'month', 'date', 'time', 'notes'];
    const lines = [columns.map(csvCell).join(',')];
    for (const item of manifest.items) {
      const row = { ...item, ...(reviews[item.id] ?? emptyReview) } as Record<string, unknown>;
      lines.push(columns.map((column) => csvCell(row[column])).join(','));
    }
    downloadFile('photo-date-review.csv', `\uFEFF${lines.join('\n')}`, 'text/csv;charset=utf-8');
  }

  async function importJson(file: File | undefined) {
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      const next: Record<string, Review> = {};
      for (const value of payload.reviews ?? []) if (value.id) next[value.id] = { decision: value.decision ?? 'unset', precision: value.precision ?? 'month', month: value.month ?? '', date: value.date ?? '', time: value.time ?? '', notes: value.notes ?? '', updatedAt: value.updatedAt ?? '' };
      setReviews(next);
    } catch { window.alert('无法导入该 JSON 文件，请确认它由本工具导出。'); }
  }

  if (loadError) return <main className="grid min-h-screen place-items-center bg-background p-8"><div className="max-w-md rounded-3xl border bg-card p-8 text-center shadow-sm"><ImageOff className="mx-auto mb-4 size-8 text-destructive" /><h1 className="text-xl font-semibold">照片清单加载失败</h1><p className="mt-2 text-sm text-muted-foreground">{loadError}</p></div></main>;
  if (!manifest) return <main className="min-h-screen animate-pulse bg-background" />;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-background/92 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1680px] items-center gap-5 px-4 py-3 lg:px-8">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2"><CalendarDays className="size-5 text-primary" /><h1 className="truncate text-base font-semibold tracking-tight">照片日期审阅台</h1><Badge variant="outline">仅保存在本机</Badge><a href="/timeline" className="text-xs text-muted-foreground hover:text-foreground">时间线整理</a></div>
            <Progress value={manifest.count ? (reviewedCount / manifest.count) * 100 : 0} className="mt-2 max-w-xl"><ProgressLabel>已完成</ProgressLabel><ProgressValue>{reviewedCount} / {manifest.count}</ProgressValue></Progress>
          </div>
          <div className="hidden items-center gap-2 md:flex"><Button variant="outline" onClick={exportJson}><FileJson />导出 JSON</Button><Button variant="outline" onClick={exportCsv}><Download />导出 CSV</Button><Button variant="ghost" onClick={() => importRef.current?.click()}><Upload />导入</Button></div>
          <input ref={importRef} type="file" accept="application/json" className="hidden" onChange={(event) => importJson(event.target.files?.[0])} />
        </div>
      </header>

      <div className="mx-auto grid max-w-[1680px] grid-cols-1 gap-5 p-4 lg:grid-cols-[minmax(0,1fr)_390px] lg:p-8">
        <section className="min-w-0 overflow-hidden rounded-3xl border bg-card shadow-[0_20px_70px_rgba(38,32,22,0.08)]">
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3 lg:px-5">
            <Select value={filter} onValueChange={(value) => setFilter(value ?? 'all')}><SelectTrigger className="w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部照片</SelectItem><SelectItem value="pending">只看未处理</SelectItem><SelectItem value="reviewed">只看已处理</SelectItem><SelectItem value="set">准备修改</SelectItem><SelectItem value="keep">保留当前日期</SelectItem><SelectItem value="skip">暂时跳过</SelectItem><SelectItem value="no_source_images">没有原片</SelectItem><SelectItem value="weak_visual_match">弱匹配候选</SelectItem></SelectContent></Select>
            <div className="relative min-w-48 flex-1"><Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索事件或文件名" className="pl-8" /></div><Badge variant="secondary">{items.length} 张</Badge>
          </div>

          {active ? <>
            <div className="relative flex min-h-[52vh] items-center justify-center bg-photo-stage p-4 lg:min-h-[68vh] lg:p-7">
              {active.thumbnail ? <button className="group relative max-h-full max-w-full cursor-zoom-in" onClick={() => setExpandedImage(active.thumbnail)} aria-label="放大当前照片"><img src={active.thumbnail} alt={active.filename} className="max-h-[66vh] max-w-full rounded-xl object-contain shadow-2xl ring-1 ring-white/10" /><span className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-black/65 px-2.5 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100"><Eye className="size-3" />放大</span></button> : <div className="grid place-items-center text-center text-stone-400"><ImageOff className="mb-3 size-10" /><p>无法生成缩略图</p></div>}
              <div className="absolute left-4 top-4 flex flex-wrap gap-2"><Badge className="bg-black/65 text-white">{active.kind}</Badge><Badge className="bg-black/65 text-white">{classificationLabel(active.classification)}</Badge></div>
            </div>
            {active.candidates.length > 0 && <div className="border-t bg-muted/35 p-4 lg:p-5"><div className="mb-3 flex items-center justify-between"><div><h2 className="text-sm font-semibold">可能相关的原片</h2><p className="text-xs text-muted-foreground">仅供判断事件和月份，不代表已经确认匹配</p></div><Badge variant="outline">候选 {active.candidates.length}</Badge></div><div className="grid grid-cols-3 gap-3">{active.candidates.map((candidate) => <button key={candidate.relativePath} className="overflow-hidden rounded-xl border bg-card text-left transition hover:-translate-y-0.5 hover:shadow-md" onClick={() => candidate.thumbnail && setExpandedImage(candidate.thumbnail)}><div className="aspect-[4/3] bg-photo-stage">{candidate.thumbnail ? <img src={candidate.thumbnail} alt="候选原片" className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center"><ImageOff className="text-muted-foreground" /></div>}</div><div className="p-2"><p className="truncate text-xs font-medium">{candidate.relativePath.split('/').at(-1)}</p><p className="mt-0.5 text-[11px] text-muted-foreground">视觉距离 {candidate.phashDistance}</p></div></button>)}</div></div>}
          </> : <div className="grid min-h-[60vh] place-items-center p-8 text-center"><div><FolderOpen className="mx-auto mb-3 size-9 text-muted-foreground" /><p className="font-medium">当前筛选没有照片</p><p className="mt-1 text-sm text-muted-foreground">更换筛选条件或清除搜索词</p></div></div>}
        </section>

        <aside className="self-start rounded-3xl border bg-card p-5 shadow-[0_20px_70px_rgba(38,32,22,0.06)] lg:sticky lg:top-24">
          {active && <>
            <div className="mb-5 flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">{active.event}</p><h2 className="mt-1 break-all text-lg font-semibold leading-snug">{active.filename}</h2><p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><FolderOpen className="size-3.5" />{active.relativePath}</p></div><Badge variant="outline">{activeIndex + 1}/{items.length}</Badge></div>
            <div className="rounded-2xl border bg-muted/35 p-3.5"><p className="text-xs text-muted-foreground">当前拍摄时间</p><p className="mt-1 font-mono text-sm font-medium">{active.currentCapture || '无'}</p>{active.suggestedMonth && <p className="mt-1 text-xs text-muted-foreground">文件夹建议月份：{active.suggestedMonth}</p>}</div>
            <div className="mt-5 grid grid-cols-3 gap-2"><Button variant={review.decision === 'keep' ? 'default' : 'outline'} onClick={() => updateReview({ decision: 'keep' })}><Check />保留</Button><Button variant={review.decision === 'set' ? 'default' : 'outline'} onClick={() => { updateReview({ decision: 'set' }); monthRef.current?.focus(); }}><CalendarDays />改日期</Button><Button variant={review.decision === 'skip' ? 'secondary' : 'outline'} onClick={() => updateReview({ decision: 'skip' })}><X />跳过</Button></div>
            <div className="mt-5 space-y-4 border-t pt-5">
              <div><label className="mb-2 block text-sm font-medium">日期精度</label><div className="grid grid-cols-3 gap-2">{([['month', '只到月份'], ['day', '具体日期'], ['exact', '日期和时间']] as const).map(([value, label]) => <Button key={value} size="sm" variant={review.precision === value ? 'secondary' : 'ghost'} onClick={() => updateReview({ precision: value, decision: 'set' })}>{label}</Button>)}</div></div>
              {review.precision === 'month' ? <div><div className="mb-2 flex items-center justify-between"><label className="text-sm font-medium">大致月份</label>{active.suggestedMonth && <button className="text-xs font-medium text-primary hover:underline" onClick={() => updateReview({ month: active.suggestedMonth, decision: 'set' })}>采用 {active.suggestedMonth}</button>}</div><Input ref={monthRef} type="month" value={review.month} onChange={(event) => updateReview({ month: event.target.value, decision: 'set' })} /></div> : <div className="grid grid-cols-[1fr_118px] gap-2"><div><label className="mb-2 block text-sm font-medium">日期</label><Input type="date" value={review.date} onChange={(event) => updateReview({ date: event.target.value, decision: 'set' })} /></div><div><label className="mb-2 block text-sm font-medium">时间{review.precision !== 'exact' && <span className="font-normal text-muted-foreground">（可选）</span>}</label><Input type="time" step="1" value={review.time} onChange={(event) => updateReview({ time: event.target.value, decision: 'set' })} /></div></div>}
              <div><label className="mb-2 block text-sm font-medium">备注</label><Textarea value={review.notes} onChange={(event) => updateReview({ notes: event.target.value })} placeholder="例如：小学毕业前后、夏天、与上一张同一天……" className="min-h-20 resize-y" /></div>
            </div>
            <div className="mt-6 flex items-center gap-2 border-t pt-5"><Button variant="outline" className="flex-1" disabled={activeIndex === 0} onClick={() => move(-1)}><ArrowLeft />上一张</Button><Button className="flex-1" disabled={activeIndex >= items.length - 1} onClick={() => move(1)}>下一张<ArrowRight /></Button></div>
            <p className="mt-3 text-center text-[11px] text-muted-foreground">快捷键：← → 切换 · K 保留 · D 改日期 · S 跳过</p>
            <div className="mt-5 flex flex-wrap gap-2 md:hidden"><Button variant="outline" size="sm" onClick={exportJson}><FileJson />JSON</Button><Button variant="outline" size="sm" onClick={exportCsv}><Download />CSV</Button><Button variant="ghost" size="sm" onClick={() => importRef.current?.click()}><Upload />导入</Button></div>
            <button className="mt-5 flex w-full items-center justify-center gap-1.5 text-xs text-muted-foreground hover:text-destructive" onClick={() => { if (window.confirm('清空本机保存的全部审阅结果？')) setReviews({}); }}><RotateCcw className="size-3.5" />清空本机记录</button>
          </>}
        </aside>
      </div>
      {expandedImage && <div className="fixed inset-0 z-50 grid place-items-center bg-black/90 p-4" role="dialog" aria-modal="true" onClick={() => setExpandedImage(null)}><button className="absolute right-5 top-5 rounded-full bg-white/10 p-2 text-white hover:bg-white/20" onClick={() => setExpandedImage(null)} aria-label="关闭大图"><X /></button><img src={expandedImage} alt="放大预览" className="max-h-full max-w-full object-contain" /></div>}
    </main>
  );
}
