import { cn } from "@/lib/utils";

export function Input({ className, type, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(
        "h-10 w-full rounded-xl border border-line bg-void px-3.5 text-[13.5px] text-mist placeholder:text-faint transition-colors hover:border-[#343b30] focus:border-lime/55 focus:outline-none focus:ring-2 focus:ring-lime/12 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-24 w-full resize-y rounded-xl border border-line bg-void px-3.5 py-2.5 text-[13.5px] leading-relaxed text-mist placeholder:text-faint transition-colors hover:border-[#343b30] focus:border-lime/55 focus:outline-none focus:ring-2 focus:ring-lime/12 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-10 w-full appearance-none rounded-xl border border-line bg-void px-3.5 pr-9 text-[13.5px] text-mist transition-colors hover:border-[#343b30] focus:border-lime/55 focus:outline-none focus:ring-2 focus:ring-lime/12 disabled:opacity-50",
        "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2214%22%20height%3D%2214%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%239aa093%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[position:right_12px_center] bg-no-repeat",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Label({
  className,
  children,
  optional,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement> & { optional?: boolean }) {
  return (
    <label
      className={cn("flex items-center gap-1.5 text-[12px] font-medium text-muted", className)}
      {...props}
    >
      {children}
      {optional ? <span className="font-normal text-faint">optional</span> : null}
    </label>
  );
}

export function Field({
  label,
  hint,
  optional,
  children,
  className,
}: {
  label: string;
  hint?: string;
  optional?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label optional={optional}>{label}</Label>
      {children}
      {hint ? <p className="text-[11.5px] leading-relaxed text-faint">{hint}</p> : null}
    </div>
  );
}
