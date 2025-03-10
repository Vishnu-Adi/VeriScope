import Link from "next/link";

import { LoginForm } from "@/components/login-form";

export default function AuthenticationPage() {
  return (
    <div className="w-screen mt-40 flex-col items-center justify-center">
      <div className="">
        <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
          <div className="flex flex-col space-y-2 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              Login to you&apos;re account.
            </h1>
            <p className="text-sm text-muted-foreground">
              Don&apos; have an account?{" "}
              <Link href="/signup" className="font-semibold">
                Signup here
              </Link>
            </p>
          </div>
          <LoginForm />
          <p className="px-8 text-center text-sm text-muted-foreground">
            By clicking continue, you agree to our{" "}
            <Link
              href="/terms"
              className="underline underline-offset-4 hover:text-primary"
            >
              Terms of Service
            </Link>{" "}
            and{" "}
            <Link
              href="/privacy"
              className="underline underline-offset-4 hover:text-primary"
            >
              Privacy Policy
            </Link>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
