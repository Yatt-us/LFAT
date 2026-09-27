import { Component, ElementRef, HostListener, computed, signal, viewChild } from '@angular/core';

interface Viewer {
  name: string;
  username: string;
}

interface Summary {
  schools: number;
  access: number;
  pending: number;
  revenue: number;
}

interface AccessStatus {
  key: string;
  label: string;
  count: number;
}

interface MonthActivity {
  month: string;
  label: string;
  submitted: number;
  confirmed: number;
}

interface PendingRequest {
  school: string;
  date: string;
  amount: number;
  href: string;
}

interface PlatformLinks {
  schools: string;
  requests: string;
  users: string;
  documents: string;
  passwordChange: string;
  logout: string;
}

interface PlatformAdminData {
  viewer: Viewer;
  summary: Summary;
  access: AccessStatus[];
  monthly: MonthActivity[];
  pending: PendingRequest[];
  links: PlatformLinks;
  csrfToken: string;
}

interface DonutSegment extends AccessStatus {
  color: string;
  dashArray: string;
  dashOffset: number;
}

const CIRCUMFERENCE = 2 * Math.PI * 58;
const STATUS_COLORS: Record<string, string> = {
  active: '#18a78d',
  trial: '#6788f5',
  expired: '#f3a746',
  suspended: '#ee7480',
};

function number(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function string(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function readData(): PlatformAdminData {
  let payload: Partial<PlatformAdminData> = {};

  if (typeof document !== 'undefined') {
    const source = document.getElementById('platform-admin-data')?.textContent;
    if (source) {
      try {
        payload = JSON.parse(source) as Partial<PlatformAdminData>;
      } catch {
        // Keep the console usable when the server sends incomplete JSON.
      }
    }
  }

  const links = payload.links;
  const summary = payload.summary;

  return {
    viewer: {
      name: string(payload.viewer?.name, 'Administrateur'),
      username: string(payload.viewer?.username),
    },
    summary: {
      schools: number(summary?.schools),
      access: number(summary?.access),
      pending: number(summary?.pending),
      revenue: number(summary?.revenue),
    },
    access: Array.isArray(payload.access)
      ? payload.access.map((item) => ({
          key: string(item.key),
          label: string(item.label),
          count: number(item.count),
        }))
      : [],
    monthly: Array.isArray(payload.monthly)
      ? payload.monthly.map((item) => ({
          month: string(item.month),
          label: string(item.label),
          submitted: number(item.submitted),
          confirmed: number(item.confirmed),
        }))
      : [],
    pending: Array.isArray(payload.pending)
      ? payload.pending.map((item) => ({
          school: string(item.school),
          date: string(item.date),
          amount: number(item.amount),
          href: string(item.href, '#'),
        }))
      : [],
    links: {
      schools: string(links?.schools, '#'),
      requests: string(links?.requests, '#'),
      users: string(links?.users, '#'),
      documents: string(links?.documents, '#'),
      passwordChange: string(links?.passwordChange, '#'),
      logout: string(links?.logout, '#'),
    },
    csrfToken: string(payload.csrfToken),
  };
}

@Component({
  selector: 'platform-admin-root',
  imports: [],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly data = readData();
  protected readonly menuOpen = signal(false);
  protected readonly period = signal<3 | 6>(6);
  protected readonly selectedMonth = signal<string | null>(null);
  protected readonly menuButton = viewChild<ElementRef<HTMLButtonElement>>('menuButton');
  protected readonly firstNavLink = viewChild<ElementRef<HTMLAnchorElement>>('firstNavLink');

  protected readonly currentDate = new Intl.DateTimeFormat('fr-FR', {
    month: 'long',
    year: 'numeric',
  }).format(new Date());

  protected readonly initials = this.data.viewer.name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('') || 'AD';

  protected readonly visibleMonthly = computed(() => this.data.monthly.slice(-this.period()));

  protected readonly chartMax = computed(() => Math.max(
    1,
    ...this.visibleMonthly().flatMap((month) => [month.submitted, month.confirmed]),
  ));

  protected readonly activeMonth = computed(() => {
    const months = this.visibleMonthly();
    return months.find((month) => month.month === this.selectedMonth()) ?? months.at(-1) ?? null;
  });

  protected readonly accessTotal = computed(() =>
    this.data.access.reduce((sum, item) => sum + item.count, 0),
  );

  protected readonly donutSegments = computed<DonutSegment[]>(() => {
    const total = this.accessTotal();
    let offset = 0;

    return this.data.access.map((item) => {
      const length = total ? (item.count / total) * CIRCUMFERENCE : 0;
      const visibleLength = Math.max(0, length - (length > 2 ? 2 : 0));
      const segment = {
        ...item,
        color: STATUS_COLORS[item.key] ?? '#a4adc5',
        dashArray: String(visibleLength) + ' ' + String(CIRCUMFERENCE),
        dashOffset: -offset,
      };
      offset += length;
      return segment;
    });
  });

  protected formatNumber(value: number): string {
    return new Intl.NumberFormat('fr-FR').format(value);
  }

  protected formatMoney(value: number): string {
    return this.formatNumber(value) + ' FCFA';
  }

  protected barHeight(value: number): number {
    return (value / this.chartMax()) * 100;
  }

  protected setPeriod(value: 3 | 6): void {
    this.period.set(value);
  }

  protected selectMonth(month: string): void {
    this.selectedMonth.set(month);
  }

  protected toggleMenu(): void {
    const open = !this.menuOpen();
    this.menuOpen.set(open);
    if (open) {
      requestAnimationFrame(() => this.firstNavLink()?.nativeElement.focus());
    }
  }

  protected closeMenu(restoreFocus = false): void {
    this.menuOpen.set(false);
    if (restoreFocus) {
      requestAnimationFrame(() => this.menuButton()?.nativeElement.focus());
    }
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (this.menuOpen()) {
      this.closeMenu(true);
    }
  }
}
