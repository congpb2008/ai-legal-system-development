import { FormEvent, useState } from "react";
import { Loader2, LockKeyhole, Mail, Scale, ShieldCheck } from "lucide-react";
import { api, ApiError } from "../api";
import type { User } from "../types";

type Props = {
  onAuthenticated: (user: User) => void;
};

export function AuthScreen({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      onAuthenticated(response.user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không thể kết nối tới máy chủ.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-brand-panel">
        <div className="brand-mark">
          <Scale size={26} strokeWidth={1.8} />
        </div>
        <p className="eyebrow">Thư viện pháp chế nội bộ</p>
        <h1>Tra cứu văn bản pháp luật, có căn cứ và có nguồn.</h1>
        <p className="auth-lede">
          Tìm đúng điều, khoản, điểm trong kho văn bản của ngân hàng. Câu trả lời luôn đi kèm nguồn trích dẫn và vị trí
          trang để đối chiếu.
        </p>
        <div className="auth-points">
          <div>
            <ShieldCheck size={18} />
            <span>Dữ liệu lưu tại chỗ, không gửi văn bản ra ngoài.</span>
          </div>
          <div>
            <ShieldCheck size={18} />
            <span>Phân cấp Chương → Mục → Điều → Khoản → Điểm.</span>
          </div>
          <div>
            <ShieldCheck size={18} />
            <span>Mọi lượt truy cập quản trị đều được ghi nhật ký.</span>
          </div>
        </div>
      </div>

      <div className="auth-form-panel">
        <div className="auth-card">
          <div className="auth-card-head">
            <p className="eyebrow">Chào mừng trở lại</p>
            <h2>{mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}</h2>
            <p>Dùng tài khoản nội bộ để truy cập thư viện dùng chung.</p>
          </div>

          <div className="segmented">
            <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">
              Đăng nhập
            </button>
            <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">
              Đăng ký
            </button>
          </div>

          <form onSubmit={submit} className="auth-form">
            <label>
              <span>Email</span>
              <div className="input-with-icon">
                <Mail size={17} />
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="ten@nganhang.vn"
                />
              </div>
            </label>
            <label>
              <span>Mật khẩu</span>
              <div className="input-with-icon">
                <LockKeyhole size={17} />
                <input
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  minLength={6}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Tối thiểu 6 ký tự"
                />
              </div>
            </label>

            {error && <div className="form-error">{error}</div>}

            <button className="primary-button auth-submit" disabled={busy} type="submit">
              {busy ? <Loader2 className="spin" size={18} /> : null}
              {mode === "login" ? "Vào thư viện" : "Tạo tài khoản và vào thư viện"}
            </button>
          </form>

          <p className="auth-footnote">
            Tài khoản quản trị đầu tiên được tạo từ cấu hình máy chủ. Liên hệ quản trị viên nếu bạn chưa có quyền truy
            cập.
          </p>
        </div>
      </div>
    </div>
  );
}
