import { redirect } from "next/navigation";

export default function RegisterDisabledPage() {
  redirect("/admin/login");
}
