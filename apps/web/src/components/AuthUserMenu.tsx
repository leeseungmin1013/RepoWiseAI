"use client";

import type { AuthChangeEvent, Session, User } from "@supabase/supabase-js";
import { LogIn, LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export function AuthUserMenu() {
  const router = useRouter();
  const client = useMemo(() => getSupabaseBrowserClient(), []);
  const configured = Boolean(client);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(configured);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!client) return;
    let active = true;
    void client.auth.getSession().then(({ data }: { data: { session: Session | null } }) => {
      if (!active) return;
      setUser(data.session?.user ?? null);
      setLoading(false);
    });
    const { data } = client.auth.onAuthStateChange((
      _event: AuthChangeEvent,
      session: Session | null,
    ) => {
      if (active) setUser(session?.user ?? null);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [client]);

  async function logout() {
    if (!client || busy) return;
    setBusy(true);
    await client.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  if (loading) {
    return <span aria-label="계정 확인 중" className="auth-user-loading" />;
  }
  if (!configured) {
    return <span className="local-mode-badge">로컬 모드</span>;
  }
  if (!user) {
    return (
      <Link className="header-account-link" href="/login?next=/">
        <LogIn aria-hidden size={14} /> 로그인
      </Link>
    );
  }

  return (
    <div className="auth-user-menu">
      <Link className="header-account-link" href="/account" title={user.email ?? "계정"}>
        <UserRound aria-hidden size={14} />
        <span>{user.email ?? "내 계정"}</span>
      </Link>
      <button aria-label="로그아웃" disabled={busy} onClick={() => void logout()} type="button">
        <LogOut aria-hidden size={14} />
      </button>
    </div>
  );
}