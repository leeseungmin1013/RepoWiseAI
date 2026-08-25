"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  type FeatureLimit,
  type Me,
  type UsageCurrent,
  type UsageEvent,
  type UsageReconciliation,
} from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

function credits(value: number) {
  return (value / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export default function AccountPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [usage, setUsage] = useState<UsageCurrent | null>(null);
  const [limits, setLimits] = useState<FeatureLimit[]>([]);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [reconciliation, setReconciliation] = useState<UsageReconciliation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [bonusCredits, setBonusCredits] = useState("10");
  const [bonusReason, setBonusReason] = useState("");
  const [bonusReference, setBonusReference] = useState("");
  const [granting, setGranting] = useState(false);

  async function loadOrganization(profile: Me) {
    const organizationId = profile.active_organization.id;
    const [current, featureLimits, recent] = await Promise.all([
      api.currentUsage(organizationId),
      api.featureLimits(organizationId),
      api.usageEvents(organizationId),
    ]);
    setUsage(current);
    setLimits(featureLimits);
    setEvents(recent);
    if (["owner", "admin"].includes(profile.active_organization.role ?? "")) {
      setReconciliation(await api.usageReconciliation());
    }
  }

  useEffect(() => {
    void api
      .me()
      .then(async (profile) => {
        setMe(profile);
        localStorage.setItem("repowise.organization", profile.active_organization.id);
        await loadOrganization(profile);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "사용량을 불러오지 못했습니다."),
      );
  }, []);

  const percent = useMemo(() => {
    const total = usage
      ? usage.allowance_micro_usd + usage.bonus_available_micro_usd
      : 0;
    return usage && total > 0
      ? Math.min(100, Math.round((usage.consumed_micro_usd / total) * 100))
      : 0;
  }, [usage]);
  const isAdmin = ["owner", "admin"].includes(me?.active_organization.role ?? "");
  const usageAlert =
    percent >= 100
      ? "월간 한도를 모두 사용했습니다. 새 비용 작업은 다음 초기화 또는 bonus 지급 전까지 차단됩니다."
      : percent >= 90
        ? "월간 한도의 90% 이상을 사용했습니다. 큰 분석·심층 작업 전에 잔여량을 확인해 주세요."
        : percent >= 70
          ? "월간 한도의 70% 이상을 사용했습니다."
          : null;

  async function logout() {
    await getSupabaseBrowserClient()?.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  async function grantBonus(event: FormEvent) {
    event.preventDefault();
    if (!me) return;
    const amount = Number(bonusCredits);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("지급할 credits를 양수로 입력해 주세요.");
      return;
    }
    setGranting(true);
    setError(null);
    setNotice(null);
    try {
      await api.grantBonusCredit(me.active_organization.id, {
        amount_micro_usd: Math.round(amount * 1_000_000),
        reason: bonusReason,
        reference: bonusReference,
      });
      setNotice(`${amount.toLocaleString()} bonus credits를 지급했습니다.`);
      setBonusReason("");
      setBonusReference("");
      await loadOrganization(me);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Bonus 지급에 실패했습니다.");
    } finally {
      setGranting(false);
    }
  }

  return (
    <main className="usage-shell">
      <header>
        <div>
          <span className="auth-kicker">RepoWise AI</span>
          <h1>계정 및 사용량</h1>
          <p>
            {me?.user.email ?? "사용자"} · {me?.active_organization.name ?? "workspace"}
          </p>
        </div>
        <div className="usage-actions">
          <Link href="/">분석 화면</Link>
          <button onClick={() => void logout()}>로그아웃</button>
        </div>
      </header>
      {error && <div className="auth-message">{error}</div>}
      {notice && <div className="auth-message">{notice}</div>}
      {usageAlert && <div className="usage-alert" role="alert">{usageAlert}</div>}
      <section className="usage-grid">
        <article>
          <span>남은 credits</span>
          <strong>{usage ? credits(usage.remaining_micro_usd) : "—"}</strong>
          <div className="usage-meter">
            <i style={{ width: `${percent}%` }} />
          </div>
          <small>
            {percent}% 사용 · {usage ? new Date(usage.period_end).toLocaleDateString() : "—"} 초기화
          </small>
        </article>
        <article>
          <span>기본 / bonus</span>
          <strong>
            {usage
              ? `${credits(usage.allowance_micro_usd)} / ${credits(usage.bonus_available_micro_usd)}`
              : "—"}
          </strong>
          <small>예약 {usage ? credits(usage.reserved_micro_usd) : "—"} credits</small>
        </article>
        <article>
          <span>Cache 절감 요청</span>
          <strong>{events.filter((item) => item.cache_status !== "miss").length}</strong>
          <small>최근 원장 기준</small>
        </article>
      </section>
      <section className="usage-panel">
        <h2>기능별 hard limit</h2>
        {limits.length ? (
          <div className="usage-list">
            {limits.map((item) => (
              <div key={item.feature}>
                <strong>{item.feature}</strong>
                <span>
                  {item.request_limit ?? "무제한"} requests · 동시 {item.concurrent_limit ?? "무제한"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p>설정된 기능별 제한이 없습니다.</p>
        )}
      </section>
      <section className="usage-panel">
        <h2>최근 사용 원장</h2>
        <div className="usage-list">
          {events.slice(0, 20).map((item) => (
            <div key={item.id}>
              <strong>{item.feature}</strong>
              <span>
                {credits(item.settled_cost_micro_usd)} credits · {item.cache_status} ·{" "}
                {new Date(item.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      </section>
      {isAdmin ? (
        <section className="usage-panel">
          <h2>관리자 운영</h2>
          <p>
            reconciliation: pending {reconciliation?.pending_reconciliation ?? "—"} · stale {reconciliation?.stale_reservations ?? "—"} · invalid cache {reconciliation?.invalid_cache_entries ?? "—"}
          </p>
          <form className="auth-form" onSubmit={(event) => void grantBonus(event)}>
            <label>
              Bonus credits
              <input value={bonusCredits} onChange={(event) => setBonusCredits(event.target.value)} inputMode="decimal" required />
            </label>
            <label>
              지급 사유
              <input value={bonusReason} onChange={(event) => setBonusReason(event.target.value)} minLength={2} required />
            </label>
            <label>
              참조 번호
              <input value={bonusReference} onChange={(event) => setBonusReference(event.target.value)} required />
            </label>
            <button disabled={granting}>{granting ? "지급 중…" : "Bonus 지급"}</button>
          </form>
        </section>
      ) : null}
    </main>
  );
}
