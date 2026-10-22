'use client';

import { useEffect, useMemo, useState } from 'react';
import { Check, Download, FileVideo, FolderSearch, Images, Search, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';

type Category = 'icloud_photo_unselected' | 'icloud_not_found' | 'nas_only' | 'icloud_video_only';
type Decision = 'add_favorite' | 'import_to_nas' | 'icloud_only' | 'keep_nas' | 'remove_favorite' | 'add_to_icloud' | 'keep_video' | 'ignore' | '';
type Item = {
  id: string; category: Category; side: 'icloud' | 'nas'; filename: string; relativePath: string;
  size: number; preview: string | null; matchedPath: string | null; matchedPreview: string | null;
  evidence: string; suggestedDecision: Decision;
};
type Manifest = {
  version: number; generatedAt: string;
  summary: Record<string, number>;
  items: Item[];
};

const STORAGE_KEY = 'favorites-compare-review-v1';
const CATEGORY_LABELS: Record<Category | 'all', string> = {
  all: '全部差异',
  icloud_photo_unselected: 'photo 有但未精选',
  icloud_not_found: 'NAS 找不到',
  nas_only: 'iCloud 没有',
  icloud_video_only: 'iCloud 视频',
};

const DECISIONS: Record<Category, Array<[Decision, string]>> = {
  icloud_photo_unselected: [['add_favorite', '设为精选'], ['icloud_only', '仅留 iCloud'], ['ignore', '暂不处理']],
  icloud_not_found: [['import_to_nas', '导回 NAS'], ['icloud_only', '仅留 iCloud'], ['ignore', '暂不处理']],
  nas_only: [['keep_nas', '保留 NAS 精选'], ['remove_favorite', '取消精选'], ['add_to_icloud', '以后补到 iCloud']],
  icloud_video_only: [['keep_video', '保留视频'], ['ignore', '不纳入精选']],
};

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}

function sizeLabel(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function FavoritesComparePage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [category, setCategory] = useState<Category | 'all'>('all');
  const [pendingOnly, setPendingOnly] = useState(true);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`/favorites-compare/manifest.json?v=${Date.now()}`, { cache: 'no-store' })
      .then((response) => { if (!response.ok) throw new Error('无法读取差异清单'); return response.json(); })
      .then(setManifest).catch((reason) => setError(reason instanceof Error ? reason.message : '加载失败'));
    try { setDecisions(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')); } catch { setDecisions({}); }
  }, []);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions)); }, [decisions]);

  const reviewed = manifest?.items.filter((item) => decisions[item.id]).length ?? 0;
  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (manifest?.items ?? []).filter((item) =>
      (category === 'all' || item.category === category) &&
      (!pendingOnly || !decisions[item.id]) &&
      (!needle || `${item.filename} ${item.relativePath} ${item.matchedPath ?? ''}`.toLowerCase().includes(needle)),
    );
  }, [manifest, category, pendingOnly, query, decisions]);

  function choose(item: Item, decision: Decision) {
    setDecisions((current) => ({ ...current, [item.id]: current[item.id] === decision ? '' : decision }));
  }

  function exportResult() {
    if (!manifest) return;
    download('favorites-difference-review.json', JSON.stringify({
      version: 1, exportedAt: new Date().toISOString(), sourceGeneratedAt: manifest.generatedAt,
      total: manifest.items.length, reviewed,
      reviews: manifest.items.map((item) => ({
        id: item.id, category: item.category, relativePath: item.relativePath,
        matchedPath: item.matchedPath, decision: decisions[item.id] ?? '',
      })),
    }, null, 2));
  }

  if (error) return <main className="grid min-h-screen place-items-center p-8 text-destructive">{error}</main>;
  if (!manifest) return <main className="min-h-screen animate-pulse bg-background" />;

  const categories: Array<Category | 'all'> = ['all', 'icloud_photo_unselected', 'icloud_not_found', 'nas_only', 'icloud_video_only'];
  const counts: Record<string, number> = { all: manifest.items.length };
  for (const item of manifest.items) counts[item.category] = (counts[item.category] ?? 0) + 1;

  return <main className="min-h-screen bg-background text-foreground">
    <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1760px] items-center gap-4 px-4 py-3 lg:px-7">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><FolderSearch className="size-5 text-primary"/><h1 className="font-semibold">iCloud / NAS 精选差异审核</h1><Badge variant="outline">本机私密 · 无图片缓存</Badge></div>
          <Progress value={manifest.items.length ? reviewed / manifest.items.length * 100 : 0} className="mt-2 max-w-xl"><ProgressLabel>已决定</ProgressLabel><ProgressValue>{reviewed}/{manifest.items.length}</ProgressValue></Progress>
        </div>
        <Button onClick={exportResult}><Download/>导出决定</Button>
      </div>
    </header>

    <div className="mx-auto max-w-[1760px] space-y-4 p-4 lg:p-7">
      <section className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ['iCloud 文件', manifest.summary.icloudFiles, '705 图 · 4 视频'],
          ['NAS 精选', manifest.summary.nasFavorites, '当前根目录'],
          ['两边匹配', manifest.summary.matchedImages, '无需处理'],
          ['iCloud 独有', manifest.summary.icloud_photo_unselected + manifest.summary.icloud_not_found, '83 可在 photo 找到'],
          ['NAS 独有', manifest.summary.nas_only, 'iCloud 未匹配'],
        ].map(([label, value, detail]) => <div key={String(label)} className="rounded-2xl border bg-card p-3 shadow-sm"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p><p className="text-[11px] text-muted-foreground">{detail}</p></div>)}
      </section>

      <section className="sticky top-[77px] z-30 space-y-2 rounded-2xl border bg-background/95 p-3 backdrop-blur-xl">
        <div className="flex flex-wrap gap-2">{categories.map((value) => <Button key={value} size="sm" variant={category === value ? 'default' : 'outline'} onClick={() => setCategory(value)}>{CATEGORY_LABELS[value]} <Badge variant="secondary" className="ml-1">{counts[value] ?? 0}</Badge></Button>)}</div>
        <div className="flex gap-2"><div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"/><Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名或相册路径"/></div><Button variant={pendingOnly ? 'secondary' : 'outline'} onClick={() => setPendingOnly((value) => !value)}>{pendingOnly ? '仅待决定' : '显示全部'}</Button><Badge variant="outline" className="px-3">当前 {items.length} 项</Badge></div>
      </section>

      <section className="grid gap-3 xl:grid-cols-2">
        {items.map((item) => {
          const selected = decisions[item.id] ?? '';
          return <article key={item.id} className="overflow-hidden rounded-2xl border bg-card shadow-sm">
            <div className={`grid bg-photo-stage ${item.matchedPreview ? 'grid-cols-2' : 'grid-cols-1'}`}>
              <div className="relative grid h-52 place-items-center border-r border-white/10">{item.preview ? <img src={item.preview} alt={item.filename} loading="lazy" className="h-full w-full object-contain"/> : <FileVideo className="size-12 text-stone-400"/>}<Badge className="absolute left-2 top-2 bg-black/65 text-white">{item.side === 'icloud' ? 'iCloud' : 'NAS 精选'}</Badge></div>
              {item.matchedPreview && <div className="relative grid h-52 place-items-center"><img src={item.matchedPreview} alt={item.matchedPath ?? ''} loading="lazy" className="h-full w-full object-contain"/><Badge className="absolute left-2 top-2 bg-black/65 text-white">NAS photo</Badge></div>}
            </div>
            <div className="space-y-3 p-4">
              <div><div className="flex items-start justify-between gap-3"><h2 className="break-all font-medium">{item.filename}</h2><Badge variant="secondary">{sizeLabel(item.size)}</Badge></div><p className="mt-1 break-all text-xs text-muted-foreground">{item.relativePath}</p>{item.matchedPath && <p className="mt-1 break-all text-xs text-primary">对应：{item.matchedPath}</p>}</div>
              <p className="rounded-xl bg-muted/45 p-2.5 text-xs leading-5">{item.evidence}</p>
              <div className="flex flex-wrap gap-2">{DECISIONS[item.category].map(([value, label]) => <Button key={value} size="sm" variant={selected === value ? 'default' : 'outline'} onClick={() => choose(item, value)}>{selected === value && <Check/>}{label}</Button>)}{selected && <Button size="sm" variant="ghost" onClick={() => choose(item, selected)}><X/>清除</Button>}</div>
            </div>
          </article>;
        })}
      </section>
      {items.length === 0 && <div className="grid min-h-48 place-items-center rounded-2xl border bg-card text-sm text-muted-foreground"><Images className="mb-2 size-8"/>当前筛选下没有待处理项目</div>}
    </div>
  </main>;
}
