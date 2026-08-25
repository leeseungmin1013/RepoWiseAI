"use client";
import { FormEvent, useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState(""); const [message, setMessage] = useState<string | null>(null);
  async function submit(event: FormEvent) { event.preventDefault(); const client = getSupabaseBrowserClient(); if (!client) return setMessage("Supabase 환경 변수가 설정되지 않았습니다."); const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: `${location.origin}/auth/callback?next=/` }); setMessage(error?.message ?? "비밀번호 재설정 메일을 보냈습니다."); }
  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}><span className="auth-kicker">RepoWise AI</span><h1>비밀번호 재설정</h1><p>가입한 이메일로 재설정 링크를 보냅니다.</p><label>이메일<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>{message && <div className="auth-message">{message}</div>}<button type="submit">재설정 메일 보내기</button><div className="auth-links"><a href="/login">로그인으로 돌아가기</a></div></form></main>;
}
