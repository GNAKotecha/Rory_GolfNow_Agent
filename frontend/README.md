# Rory Frontend

Lightweight Next.js frontend for the Rory AI Assistant.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure backend URL in `.env.local`:
```bash
NEXT_PUBLIC_API_URL=https://your-runpod-url
```

3. Run development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

## Features

- 🔐 Authentication (login/logout)
- 💬 Real-time chat interface
- 📝 Session management
- 🎨 Dark theme UI
- 📱 Responsive design

## Structure

```
frontend/
├── app/
│   ├── login/page.tsx       # Login page
│   ├── chat/page.tsx        # Main chat interface
│   ├── page.tsx             # Home (redirects)
│   └── layout.tsx           # Root layout
├── contexts/
│   └── AuthContext.tsx      # Auth state management
├── lib/
│   └── api.ts              # Backend API client
└── .env.local              # Environment config
```

## Deployment

```bash
npm run build
npm start
```

Or deploy to Vercel:
```bash
vercel deploy
```
