import './globals.css';

export const metadata = {
  title: 'RE-ENTRY',
  description: 'Market re-entry intelligence',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
