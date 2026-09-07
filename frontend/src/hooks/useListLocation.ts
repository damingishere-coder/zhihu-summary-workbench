import { useSearchParams } from "react-router-dom";

/** Filters live in the URL so back/forward and shared links restore the same list. */
export function useListLocation() {
  const [params, setParams] = useSearchParams();
  const get = (key: string, fallback = "") => params.get(key) ?? fallback;
  const set = (key: string, value: string | number) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (String(value)) next.set(key, String(value));
        else next.delete(key);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  const rawPage = Number(get("page", "1"));
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  return { get, set, page };
}
