'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, ArrowRight, CalendarRange, Check, Copy, Database, Eye, FileJson, FolderInput, ImageOff, Plus, Search, Sparkles, Tags, Upload, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';

type Visual = { dhash: number; ahash: number; color: number[]; sharpness: number };
type Item = { id: string; filename: string; relativePath: string; currentFolder: string; location: 'library' | 'backup' | 'unassigned'; subdir: string; preclassified?: boolean; kind: 'image' | 'video'; format: string; bytes: number; width: number; height: number; captureDate: string | null; createDate: string | null; fileModifyDate: string | null; dateSource: string; metadataStatus: string; expectedFolder: string | null; timelineMismatch: boolean; thumbnail: string | null; visual?: Visual | null; duplicateGroupIds?: string[] };
type DuplicateGroup = { id: string; type: 'exact' | 'visual'; memberIds: string[]; recommendedId: string; intentionalBackup: boolean };
type Manifest = { generatedAt: string; stats: { items: number; libraryItems: number; backupItems: number; unassignedItems: number; timelineMismatches: number; exactDuplicateGroups: number; visualDuplicateGroups: number; metadataIssues: number }; folders: { name: string; startDate: string }[]; items: Item[]; duplicateGroups: DuplicateGroup[] };
type Decision = { targetFolder?: string; duplicateAction?: 'keep' | 'backup' | 'skip'; correctedDate?: string; notes?: string; tags?: string[]; updatedAt: string };

const STORAGE_KEY = 'photo-timeline-review-v1';
const TAGS_KEY = 'photo-timeline-tags-v1';
const SHORTCUT_CODES = ['Backquote', 'Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5', 'Digit6', 'Digit7', 'Digit8', 'Digit9', 'Digit0', 'Minus', 'Equal', 'KeyQ', 'KeyW', 'KeyE', 'KeyR', 'KeyT', 'KeyY', 'KeyU', 'KeyI', 'KeyO', 'KeyP', 'BracketLeft', 'BracketRight'];
const SHORTCUT_LABELS = ['·', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']'];

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url);
}

function bytes(value: number) {
  if (!value) return '未知大小';
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.round(value / 1024)} KB`;
}

function statusLabel(value: string) {
  return ({ consistent: '时间一致', 'fallback-date': '使用备用日期', missing: '缺少日期', 'capture-create-conflict': '拍摄/创建冲突', 'bulk-date-anomaly': '批量错误日期' } as Record<string, string>)[value] ?? value;
}

function actionLabel(value?: Decision['duplicateAction']) {
  return ({ keep: '保留此版本', backup: '移入备份', skip: '暂不处理' } as Record<string, string>)[value ?? ''] ?? '未决定';
}

export default function TimelinePage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [tagLibrary, setTagLibrary] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [reviewIndex, setReviewIndex] = useState(0);
  const [query, setQuery] = useState('');
  const [timelineFilter, setTimelineFilter] = useState('all');
  const [folderFilter, setFolderFilter] = useState('all');
  const [duplicateFilter, setDuplicateFilter] = useState('all');
  const [metadataFilter, setMetadataFilter] = useState('issues');
  const [showIntentional, setShowIntentional] = useState(false);
  const [limit, setLimit] = useState(120);
  const [active, setActive] = useState<Item | null>(null);
  const [error, setError] = useState('');
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/timeline/timeline-items.json')
      .then((response) => { if (!response.ok) throw new Error('无法读取时间线数据'); return response.json(); })
      .then(setManifest)
      .catch((reason) => setError(reason instanceof Error ? reason.message : '加载失败'));
    try { setDecisions(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')); } catch { /* Ignore malformed local state. */ }
    try { setTagLibrary(JSON.parse(localStorage.getItem(TAGS_KEY) ?? '[]')); } catch { /* Ignore malformed local state. */ }
  }, []);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions)); }, [decisions]);
  useEffect(() => { localStorage.setItem(TAGS_KEY, JSON.stringify(tagLibrary)); }, [tagLibrary]);
  useEffect(() => { setLimit(120); }, [query, timelineFilter, folderFilter, duplicateFilter, metadataFilter, showIntentional]);
  useEffect(() => { setReviewIndex(0); }, [query, timelineFilter, folderFilter]);

  const itemById = useMemo(() => new Map(manifest?.items.map((item) => [item.id, item]) ?? []), [manifest]);
  const reviewed = manifest?.items.filter((item) => !!decisions[item.id]).length ?? 0;

  function decide(id: string, patch: Partial<Decision>) {
    setDecisions((current) => ({ ...current, [id]: { ...current[id], ...patch, updatedAt: new Date().toISOString() } }));
  }

  function toggleTag(id: string, tag: string) {
    const tags = new Set(decisions[id]?.tags ?? []);
    if (tags.has(tag)) tags.delete(tag); else tags.add(tag);
    decide(id, { tags: [...tags] });
  }

  function addTag(id?: string) {
    const tag = tagInput.trim();
    if (!tag) return;
    setTagLibrary((current) => current.includes(tag) ? current : [...current, tag]);
    if (id && !(decisions[id]?.tags ?? []).includes(tag)) toggleTag(id, tag);
    setTagInput('');
  }

  function matches(item: Item) {
    const value = query.trim().toLowerCase();
    return !value || `${item.filename} ${item.relativePath} ${item.currentFolder} ${item.captureDate ?? ''}`.toLowerCase().includes(value);
  }

  const timelineItems = useMemo(() => {
    if (!manifest) return [];
    return manifest.items.filter((item) => {
      const filterMatch = (timelineFilter === 'all' && item.location !== 'backup' && !item.preclassified)
        || (timelineFilter === 'mismatch' && item.timelineMismatch)
        || (timelineFilter === 'backup' && item.location === 'backup')
        || (timelineFilter === 'unassigned' && item.location === 'unassigned')
        || (timelineFilter === 'metadata' && item.metadataStatus !== 'consistent')
        || (timelineFilter === 'classified' && item.preclassified)
        || (timelineFilter === 'reviewed' && !!decisions[item.id])
        || (timelineFilter === 'pending' && !decisions[item.id]);
      return filterMatch && (folderFilter === 'all' || item.currentFolder === folderFilter) && matches(item);
    }).sort((left, right) => (left.captureDate ?? '9999').localeCompare(right.captureDate ?? '9999'));
  }, [manifest, timelineFilter, folderFilter, query, decisions]);

  const duplicateGroups = useMemo(() => {
    if (!manifest) return [];
    return manifest.duplicateGroups.filter((group) => {
      if (!showIntentional && group.intentionalBackup) return false;
      if (duplicateFilter !== 'all' && group.type !== duplicateFilter) return false;
      return group.memberIds.some((id) => { const item = itemById.get(id); return item ? matches(item) : false; });
    });
  }, [manifest, showIntentional, duplicateFilter, query, itemById]);

  const metadataItems = useMemo(() => {
    if (!manifest) return [];
    return manifest.items.filter((item) => {
      const filterMatch = metadataFilter === 'all' || (metadataFilter === 'issues' && item.metadataStatus !== 'consistent') || item.metadataStatus === metadataFilter;
      return filterMatch && matches(item);
    }).sort((left, right) => left.metadataStatus.localeCompare(right.metadataStatus));
  }, [manifest, metadataFilter, query]);

  const reviewItem = timelineItems[Math.min(reviewIndex, Math.max(0, timelineItems.length - 1))];
  const tagSummary = useMemo(() => tagLibrary.map((tag) => ({ tag, items: manifest?.items.filter((item) => decisions[item.id]?.tags?.includes(tag)) ?? [] })), [manifest, tagLibrary, decisions]);
  const taggedCount = manifest?.items.filter((item) => (decisions[item.id]?.tags?.length ?? 0) > 0).length ?? 0;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input, textarea, select, [role="combobox"], [contenteditable="true"]')) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        setReviewIndex((value) => Math.max(0, value - 1));
        return;
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        setReviewIndex((value) => Math.min(Math.max(0, timelineItems.length - 1), value + 1));
        return;
      }
      const shortcutIndex = SHORTCUT_CODES.indexOf(event.code);
      const tag = tagLibrary[shortcutIndex];
      if (shortcutIndex >= 0 && tag && reviewItem) {
        event.preventDefault();
        toggleTag(reviewItem.id, tag);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [reviewItem, tagLibrary, timelineItems.length, decisions]);

  function exportJson() {
    if (!manifest) return;
    const payload = {
      version: 1, exportedAt: new Date().toISOString(), sourceGeneratedAt: manifest.generatedAt,
      range: { from: '170901', to: '190613' }, totalItems: manifest.stats.items, reviewedItems: reviewed,
      tagLibrary, tagSummary: tagSummary.map((group) => ({ tag: group.tag, count: group.items.length, itemIds: group.items.map((item) => item.id) })),
      decisions: manifest.items.filter((item) => decisions[item.id]).map((item) => ({ id: item.id, relativePath: item.relativePath, currentFolder: item.currentFolder, expectedFolder: item.expectedFolder, captureDate: item.captureDate, ...decisions[item.id] })),
    };
    download('photo-timeline-review.json', JSON.stringify(payload, null, 2));
  }

  async function importJson(file?: File) {
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      const next: Record<string, Decision> = {};
      for (const row of payload.decisions ?? []) if (row.id) next[row.id] = { targetFolder: row.targetFolder, duplicateAction: row.duplicateAction, correctedDate: row.correctedDate, notes: row.notes, tags: row.tags ?? [], updatedAt: row.updatedAt ?? '' };
      setDecisions(next);
      setTagLibrary(payload.tagLibrary ?? []);
    } catch { window.alert('无法导入该文件，请确认它由本时间线工具导出。'); }
  }

  function acceptRecommendation(group: DuplicateGroup) {
    for (const id of group.memberIds) {
      const item = itemById.get(id);
      decide(id, { duplicateAction: id === group.recommendedId ? 'keep' : item?.location === 'backup' ? 'skip' : 'backup' });
    }
  }

  if (error) return <main className="grid min-h-screen place-items-center bg-background p-8"><p className="rounded-2xl border bg-card p-6 text-destructive">{error}</p></main>;
  if (!manifest) return <main className="min-h-screen animate-pulse bg-background" />;

  const cards = [
    { label: '全部媒体', value: manifest.stats.items, icon: Database },
    { label: '时间线待核对', value: manifest.stats.timelineMismatches, icon: CalendarRange },
    { label: '重复与相似组', value: manifest.stats.exactDuplicateGroups + manifest.stats.visualDuplicateGroups, icon: Copy },
    { label: '元数据问题', value: manifest.stats.metadataIssues, icon: AlertTriangle },
  ];

  return <main className="min-h-screen bg-background text-foreground">
    <header className="sticky top-0 z-30 border-b bg-card/92 backdrop-blur-xl">
      <div className="mx-auto max-w-[1760px] px-4 py-4 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div><div className="flex items-center gap-2"><CalendarRange className="size-5 text-primary" /><Badge variant="outline">本机私密</Badge><a href="/select" className="text-xs text-muted-foreground hover:text-foreground">精选工具</a><a href="/calibrate" className="text-xs text-muted-foreground hover:text-foreground">日期校准</a></div><h1 className="mt-1 text-2xl font-semibold tracking-tight">记忆时间线整理台</h1><p className="text-xs text-muted-foreground">170901—190613 · 已记录 {reviewed} 项决定</p></div>
          <div className="flex gap-2"><Button variant="outline" onClick={() => importRef.current?.click()}><Upload />导入</Button><Button onClick={exportJson}><FileJson />导出结果</Button><input ref={importRef} type="file" accept="application/json" className="hidden" onChange={(event) => importJson(event.target.files?.[0])} /></div>
        </div>
      </div>
    </header>

    <div className="mx-auto max-w-[1760px] p-4 lg:p-8">
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, icon: Icon }) => <div key={label} className="rounded-2xl border bg-card p-4 shadow-sm"><div className="flex items-center justify-between"><p className="text-sm text-muted-foreground">{label}</p><Icon className="size-4 text-primary" /></div><p className="mt-2 text-3xl font-semibold tabular-nums">{value.toLocaleString()}</p></div>)}</div>

      <Tabs defaultValue="timeline">
        <TabsList className="h-10"><TabsTrigger value="timeline" className="px-4">逐张标记</TabsTrigger><TabsTrigger value="tags" className="px-4">标签汇总</TabsTrigger><TabsTrigger value="duplicates" className="px-4">重复版本</TabsTrigger><TabsTrigger value="metadata" className="px-4">元数据</TabsTrigger></TabsList>
        <div className="mt-5 flex flex-wrap items-center gap-2 rounded-2xl border bg-card p-2.5 shadow-sm"><div className="relative min-w-64 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名、文件夹或拍摄日期" className="pl-9" /></div><Badge variant="secondary">本机保存 · {reviewed} 项</Badge></div>

        <TabsContent value="timeline" className="mt-4">
          <div className="mb-4 flex flex-wrap gap-2">
            <Select value={timelineFilter} onValueChange={(value) => setTimelineFilter(value ?? 'all')}><SelectTrigger className="w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">剩余待整理主库</SelectItem><SelectItem value="mismatch">只看疑似错放</SelectItem><SelectItem value="pending">只看未处理</SelectItem><SelectItem value="reviewed">只看已处理</SelectItem><SelectItem value="classified">查看已分类照片</SelectItem><SelectItem value="backup">备份中的版本</SelectItem><SelectItem value="unassigned">18 个待定视频</SelectItem><SelectItem value="metadata">时间信息异常</SelectItem></SelectContent></Select>
            <Select value={folderFilter} onValueChange={(value) => setFolderFilter(value ?? 'all')}><SelectTrigger className="w-60"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部当前文件夹</SelectItem>{manifest.folders.map((folder) => <SelectItem key={folder.name} value={folder.name}>{folder.name}</SelectItem>)}</SelectContent></Select>
            <Badge variant="outline" className="ml-auto">{timelineItems.length} 个结果</Badge>
          </div>
          {reviewItem ? <div className="grid overflow-hidden rounded-3xl border bg-card shadow-sm lg:grid-cols-[minmax(0,1.45fr)_420px]">
            <section className="relative grid min-h-[58vh] place-items-center bg-photo-stage p-4 lg:min-h-[72vh] lg:p-7">{reviewItem.thumbnail ? <img src={reviewItem.thumbnail} alt={reviewItem.filename} className="max-h-[70vh] max-w-full object-contain shadow-2xl" /> : <div className="text-center text-stone-400"><ImageOff className="mx-auto mb-3 size-10" /><p>该视频暂无缩略图</p></div>}<div className="absolute left-4 top-4 flex gap-2"><Badge className="bg-black/65 text-white">{reviewItem.location === 'backup' ? '备份' : reviewItem.kind === 'video' ? '视频' : '主库'}</Badge><Badge className="bg-black/65 text-white">{reviewIndex + 1} / {timelineItems.length}</Badge></div><Button variant="secondary" size="sm" className="absolute bottom-4 right-4" onClick={() => setActive(reviewItem)}><Eye />查看详情</Button></section>
            <aside className="flex flex-col p-5 lg:p-6"><div><p className="text-xs font-medium uppercase tracking-[.12em] text-muted-foreground">{reviewItem.currentFolder}</p><h2 className="mt-1 break-all text-lg font-semibold">{reviewItem.filename}</h2><p className="mt-2 break-all text-xs text-muted-foreground">{reviewItem.relativePath}</p></div><div className="mt-4 rounded-2xl border bg-muted/35 p-3"><p className="font-mono text-sm">{reviewItem.captureDate ?? '没有可用拍摄时间'}</p>{reviewItem.expectedFolder && reviewItem.expectedFolder !== reviewItem.currentFolder && <p className="mt-1 flex items-center gap-1 text-xs font-medium text-primary"><ArrowRight className="size-3" />建议归入 {reviewItem.expectedFolder}</p>}</div>
              <div className="mt-5 border-t pt-5"><div className="flex items-center justify-between"><div><h3 className="font-semibold">给这张照片添加标签</h3><p className="text-xs text-muted-foreground">新标签会保存，可在后续照片直接选择</p></div><Tags className="size-5 text-primary" /></div><div className="mt-3 flex gap-2"><Input value={tagInput} onChange={(event) => setTagInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') addTag(reviewItem.id); }} placeholder="输入标签，如：室友、军训、天津" /><Button onClick={() => addTag(reviewItem.id)}><Plus />保存</Button></div><div className="mt-3 flex min-h-12 flex-wrap content-start gap-2">{tagLibrary.map((tag, index) => { const chosen = decisions[reviewItem.id]?.tags?.includes(tag); const shortcut = SHORTCUT_LABELS[index]; return <button key={tag} onClick={() => toggleTag(reviewItem.id, tag)} className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-sm transition ${chosen ? 'border-primary bg-primary text-primary-foreground' : 'bg-background hover:border-primary/60'}`}>{shortcut && <kbd className={`grid min-w-5 place-items-center rounded px-1 py-0.5 font-mono text-[11px] ${chosen ? 'bg-white/20' : 'bg-muted text-muted-foreground'}`}>{shortcut}</kbd>}{chosen && <Check className="size-3" />}{tag}</button>; })}{tagLibrary.length === 0 && <p className="text-sm text-muted-foreground">还没有标签，先在上方输入第一个。</p>}</div>{tagLibrary.length > SHORTCUT_LABELS.length && <p className="mt-2 text-xs text-muted-foreground">前 {SHORTCUT_LABELS.length} 个标签支持键盘快捷键，其余标签仍可点击选择。</p>}</div>
              <div className="mt-auto pt-6"><div className="mb-3 flex flex-wrap gap-1.5">{(decisions[reviewItem.id]?.tags ?? []).map((tag) => <Badge key={tag}>{tag}</Badge>)}{!(decisions[reviewItem.id]?.tags?.length) && <Badge variant="outline">尚未标记</Badge>}</div><div className="grid grid-cols-2 gap-2"><Button variant="outline" disabled={reviewIndex === 0} onClick={() => setReviewIndex((value) => Math.max(0, value - 1))}><ArrowLeft />上一张</Button><Button disabled={reviewIndex >= timelineItems.length - 1} onClick={() => setReviewIndex((value) => Math.min(timelineItems.length - 1, value + 1))}>下一张<ArrowRight /></Button></div><p className="mt-3 text-center text-xs text-muted-foreground">快捷键：← → 切换 · ·1234567890-= · qwertyuiop[] 选择标签</p><p className="mt-1 text-center text-xs text-muted-foreground">已标记 {taggedCount} / {manifest.stats.items} 张</p></div>
            </aside>
          </div> : <div className="grid min-h-72 place-items-center rounded-3xl border border-dashed text-center text-muted-foreground">当前筛选没有照片</div>}
        </TabsContent>

        <TabsContent value="tags" className="mt-4">
          <div className="mb-4 flex flex-wrap items-center gap-2"><div className="flex min-w-72 flex-1 gap-2"><Input value={tagInput} onChange={(event) => setTagInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') addTag(); }} placeholder="继续创建标签" /><Button onClick={() => addTag()}><Plus />添加标签</Button></div><Badge variant="outline">{tagLibrary.length} 个标签 · {taggedCount} 张已标记</Badge></div>
          <div className="grid gap-4 lg:grid-cols-2">{tagSummary.map((group) => <section key={group.tag} className="rounded-3xl border bg-card p-4 shadow-sm"><div className="flex items-center justify-between"><div className="flex items-center gap-2"><Tags className="size-4 text-primary" /><h2 className="font-semibold">{group.tag}</h2></div><Badge>{group.items.length} 张</Badge></div><div className="mt-4 grid grid-cols-5 gap-2">{group.items.slice(0, 10).map((item) => <button key={item.id} className="aspect-square overflow-hidden rounded-lg bg-photo-stage" onClick={() => setActive(item)}>{item.thumbnail ? <img src={item.thumbnail} alt={item.filename} className="h-full w-full object-cover" /> : <ImageOff className="m-auto size-4 text-stone-400" />}</button>)}</div>{group.items.length === 0 && <p className="mt-4 text-sm text-muted-foreground">这个标签还没有照片。</p>}{group.items.length > 10 && <p className="mt-2 text-xs text-muted-foreground">另有 {group.items.length - 10} 张，会包含在导出结果中。</p>}</section>)}{tagLibrary.length === 0 && <div className="grid min-h-64 place-items-center rounded-3xl border border-dashed text-center text-muted-foreground lg:col-span-2"><div><Tags className="mx-auto mb-3 size-8" /><p>先在“逐张标记”中创建标签。</p></div></div>}</div>
        </TabsContent>

        <TabsContent value="duplicates" className="mt-4">
          <div className="mb-4 flex flex-wrap items-center gap-2"><Select value={duplicateFilter} onValueChange={(value) => setDuplicateFilter(value ?? 'all')}><SelectTrigger className="w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">精确 + 相似</SelectItem><SelectItem value="exact">只看完全相同</SelectItem><SelectItem value="visual">只看不同质量版本</SelectItem></SelectContent></Select><Button variant={showIntentional ? 'secondary' : 'outline'} onClick={() => setShowIntentional((value) => !value)}>{showIntentional ? '隐藏正常备份副本' : '显示正常备份副本'}</Button><Badge variant="outline" className="ml-auto">{duplicateGroups.length} 组待查看</Badge></div>
          <div className="space-y-4">{duplicateGroups.slice(0, limit).map((group, index) => {
            const members = group.memberIds.map((id) => itemById.get(id)).filter(Boolean) as Item[];
            return <section key={group.id} className="rounded-3xl border bg-card p-4 shadow-sm lg:p-5"><div className="mb-4 flex flex-wrap items-center gap-2"><Badge variant={group.type === 'visual' ? 'default' : 'secondary'}>{group.type === 'visual' ? '不同质量/格式' : '文件完全相同'}</Badge><span className="text-sm font-medium">第 {index + 1} 组 · {members.length} 个版本</span>{group.intentionalBackup && <Badge variant="outline">正常备份副本</Badge>}<Button size="sm" className="ml-auto" onClick={() => acceptRecommendation(group)}><Sparkles />采用质量建议</Button></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{members.map((item) => {
              const recommended = item.id === group.recommendedId; const choice = decisions[item.id]?.duplicateAction;
              return <article key={item.id} className={`overflow-hidden rounded-2xl border ${recommended ? 'border-primary ring-2 ring-primary/20' : ''}`}><button className="relative block aspect-[4/3] w-full bg-photo-stage" onClick={() => setActive(item)}>{item.thumbnail ? <img src={item.thumbnail} alt={item.filename} loading="lazy" className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center"><ImageOff className="text-stone-400" /></div>}{recommended && <Badge className="absolute left-2 top-2"><Sparkles />建议保留</Badge>}</button><div className="p-3"><p className="truncate text-sm font-medium">{item.filename}</p><p className="mt-1 text-xs text-muted-foreground">{item.width}×{item.height} · {bytes(item.bytes)} · {item.format.toUpperCase()}</p><p className="mt-1 truncate text-[11px] text-muted-foreground">{item.relativePath}</p><div className="mt-3 grid grid-cols-3 gap-1"><Button size="sm" variant={choice === 'keep' ? 'default' : 'ghost'} onClick={() => decide(item.id, { duplicateAction: 'keep' })}>保留</Button><Button size="sm" variant={choice === 'backup' ? 'secondary' : 'ghost'} onClick={() => decide(item.id, { duplicateAction: 'backup' })}>备份</Button><Button size="sm" variant={choice === 'skip' ? 'outline' : 'ghost'} onClick={() => decide(item.id, { duplicateAction: 'skip' })}>跳过</Button></div><p className="mt-2 text-center text-[11px] text-muted-foreground">{actionLabel(choice)}</p></div></article>;
            })}</div></section>;
          })}</div>
        </TabsContent>

        <TabsContent value="metadata" className="mt-4">
          <div className="mb-4 flex flex-wrap items-center gap-2"><Select value={metadataFilter} onValueChange={(value) => setMetadataFilter(value ?? 'issues')}><SelectTrigger className="w-52"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="issues">全部问题</SelectItem><SelectItem value="capture-create-conflict">拍摄/创建时间冲突</SelectItem><SelectItem value="fallback-date">只有备用日期</SelectItem><SelectItem value="missing">完全缺少日期</SelectItem><SelectItem value="bulk-date-anomaly">批量错误日期</SelectItem><SelectItem value="all">包含正常文件</SelectItem></SelectContent></Select><Badge variant="outline" className="ml-auto">{metadataItems.length} 个结果</Badge></div>
          <div className="overflow-hidden rounded-3xl border bg-card"><div className="divide-y">{metadataItems.slice(0, limit).map((item) => <button key={item.id} onClick={() => setActive(item)} className="grid w-full grid-cols-[72px_minmax(0,1fr)] gap-3 p-3 text-left hover:bg-muted/50 sm:grid-cols-[72px_minmax(0,1fr)_180px_170px]"><div className="h-14 overflow-hidden rounded-lg bg-photo-stage">{item.thumbnail ? <img src={item.thumbnail} alt="" className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center"><ImageOff className="size-4 text-stone-400" /></div>}</div><div className="min-w-0"><p className="truncate text-sm font-medium">{item.filename}</p><p className="truncate text-xs text-muted-foreground">{item.relativePath}</p><Badge variant={item.metadataStatus === 'bulk-date-anomaly' || item.metadataStatus === 'capture-create-conflict' ? 'destructive' : 'outline'} className="mt-1">{statusLabel(item.metadataStatus)}</Badge></div><div className="hidden sm:block"><p className="text-[11px] text-muted-foreground">拍摄时间</p><p className="mt-1 font-mono text-xs">{item.captureDate ?? '无'}</p></div><div className="hidden sm:block"><p className="text-[11px] text-muted-foreground">创建时间</p><p className="mt-1 font-mono text-xs">{item.createDate ?? '无'}</p></div></button>)}</div></div>
          {metadataItems.length > limit && <div className="mt-6 text-center"><Button variant="outline" onClick={() => setLimit((value) => value + 120)}>继续显示</Button></div>}
        </TabsContent>
      </Tabs>
    </div>

    {active && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-3 backdrop-blur-sm" role="dialog" aria-modal="true" onClick={() => setActive(null)}>
      <div className="relative max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-card shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <button className="absolute right-3 top-3 z-10 rounded-full bg-black/50 p-2 text-white hover:bg-black/70" onClick={() => setActive(null)} aria-label="关闭"><X className="size-4" /></button>
        <div className="grid lg:grid-cols-[minmax(0,1.3fr)_390px]"><div className="grid min-h-80 place-items-center bg-photo-stage p-4">{active.thumbnail ? <img src={active.thumbnail} alt={active.filename} className="max-h-[76vh] max-w-full object-contain" /> : <div className="text-center text-stone-400"><ImageOff className="mx-auto mb-2" />视频暂无预览</div>}</div><div className="p-5">
          <div><h2 className="break-all pr-8 text-lg font-semibold">{active.filename}</h2><p className="mt-1 break-all text-sm text-muted-foreground">{active.relativePath}</p></div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs"><div className="rounded-xl border p-3"><p className="text-muted-foreground">分辨率/大小</p><p className="mt-1 font-medium">{active.width || '—'}×{active.height || '—'} · {bytes(active.bytes)}</p></div><div className="rounded-xl border p-3"><p className="text-muted-foreground">时间状态</p><p className="mt-1 font-medium">{statusLabel(active.metadataStatus)}</p></div></div>
          <div className="mt-5 space-y-4"><div><label className="mb-2 block text-sm font-medium">目标文件夹</label><Select value={decisions[active.id]?.targetFolder ?? ''} onValueChange={(value) => decide(active.id, { targetFolder: value ?? undefined })}><SelectTrigger><SelectValue placeholder={active.expectedFolder ? `建议：${active.expectedFolder}` : '暂不指定'} /></SelectTrigger><SelectContent>{manifest.folders.map((folder) => <SelectItem key={folder.name} value={folder.name}>{folder.name}</SelectItem>)}</SelectContent></Select><p className="mt-1.5 text-xs text-muted-foreground">当前：{active.currentFolder}{active.expectedFolder ? ` · 系统建议：${active.expectedFolder}` : ''}</p></div>
            <div><label className="mb-2 block text-sm font-medium">修正后的拍摄/创建时间</label><Input type="datetime-local" step="1" value={decisions[active.id]?.correctedDate ?? ''} onChange={(event) => decide(active.id, { correctedDate: event.target.value })} /><div className="mt-2 flex gap-2"><Button size="sm" variant="outline" disabled={!active.captureDate} onClick={() => decide(active.id, { correctedDate: active.captureDate?.replace(' ', 'T') })}><CalendarRange />采用当前拍摄时间</Button>{active.expectedFolder && <Button size="sm" variant="ghost" onClick={() => decide(active.id, { targetFolder: active.expectedFolder ?? undefined })}><FolderInput />采用文件夹建议</Button>}</div></div>
            <div><label className="mb-2 block text-sm font-medium">版本处理</label><div className="grid grid-cols-3 gap-2"><Button variant={decisions[active.id]?.duplicateAction === 'keep' ? 'default' : 'outline'} onClick={() => decide(active.id, { duplicateAction: 'keep' })}>保留</Button><Button variant={decisions[active.id]?.duplicateAction === 'backup' ? 'secondary' : 'outline'} onClick={() => decide(active.id, { duplicateAction: 'backup' })}>移入备份</Button><Button variant={decisions[active.id]?.duplicateAction === 'skip' ? 'secondary' : 'outline'} onClick={() => decide(active.id, { duplicateAction: 'skip' })}>跳过</Button></div></div>
            <div><label className="mb-2 block text-sm font-medium">备注</label><Textarea value={decisions[active.id]?.notes ?? ''} onChange={(event) => decide(active.id, { notes: event.target.value })} placeholder="例如：和上一张同一天、应该属于开学后一周……" /></div>
          </div>
        </div></div>
      </div>
    </div>}
  </main>;
}
