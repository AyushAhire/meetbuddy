import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import { authApi } from "./api";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        try {
          const tokens = await authApi.login(
            credentials.email as string,
            credentials.password as string,
          );
          return {
            id: "user",
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            accessTokenExpires: Date.now() + 55 * 60 * 1000, // refresh 5 min before expiry
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        const u = user as Record<string, unknown>;
        token.accessToken = u.accessToken as string;
        token.refreshToken = u.refreshToken as string;
        token.accessTokenExpires = u.accessTokenExpires as number;
        return token;
      }

      // Token still valid
      if (Date.now() < (token.accessTokenExpires as number)) return token;

      // Token expired — refresh it
      try {
        const tokens = await authApi.refresh(token.refreshToken as string);
        return {
          ...token,
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          accessTokenExpires: Date.now() + 55 * 60 * 1000,
        };
      } catch {
        // Refresh failed — force re-login
        return { ...token, error: "RefreshTokenError" };
      }
    },
    async session({ session, token }) {
      (session as Record<string, unknown>).accessToken = token.accessToken;
      (session as Record<string, unknown>).error = token.error;
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
});
