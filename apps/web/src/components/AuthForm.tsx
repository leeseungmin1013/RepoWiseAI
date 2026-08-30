"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { safeNextPath } from "@/lib/auth";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setMessage("Supabase 환경 변수가 설정되지 않았습니다.");
      return;
    }
    setBusy(true);
    setMessage(null);
    const result =
      mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({
            email,
            password,
            options: { emailRedirectTo: `${location.origin}/auth/callback` },
          });
    setBusy(false);
    if (result.error) {
      setMessage(result.error.message);
      return;
    }
    if (mode === "signup" && !result.data.session) {
      setMessage("확인 메일을 보냈습니다. 이메일 인증 후 로그인해 주세요.");
      return;
    }
    router.replace(safeNextPath(params.get("next")));
    router.refresh();
  }

  return (
    <main className="auth-shell">
      <form className="auth-card" onSubmit={submit}>
        <span className="auth-kicker">RepoWise AI</span>
        <h1>{mode === "login" ? "로그인" : "계정 만들기"}</h1>
        <p>개인 workspace에서 저장소 분석과 학습 기록을 안전하게 관리합니다.</p>
        <label>이메일<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label>비밀번호<input type="password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {message && <div className="auth-message">{message}</div>}
        <button type="submit" disabled={busy}>{busy ? "처리 중…" : mode === "login" ? "로그인" : "가입하기"}</button>
        <div className="auth-links">
          <a href={mode === "login" ? "/signup" : "/login"}>{mode === "login" ? "새 계정 만들기" : "기존 계정으로 로그인"}</a>
          {mode === "login" && <a href="/forgot-password">비밀번호 찾기</a>}
        </div>
      </form>
    </main>
  );
}
