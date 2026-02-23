/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'media',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      colors: {
        n: {
          0:   '#000000',
          5:   '#0d0d0d',
          10:  '#171717',
          15:  '#212121',
          20:  '#2d2d3a',
          25:  '#3a3b44',
          30:  '#444654',
          35:  '#4e4f60',
          40:  '#565869',
          50:  '#6e6e80',
          60:  '#8e8ea0',
          70:  '#acacbe',
          80:  '#c5c5d2',
          90:  '#d9d9e3',
          95:  '#ececf1',
          98:  '#f7f7f8',
          99:  '#fafafa',
          100: '#ffffff',
        },
        p: {
          10:  '#0f1a5c',
          20:  '#1e2d7a',
          30:  '#2d419c',
          35:  '#374eaa',
          40:  '#4159b8',
          50:  '#5570d4',
          60:  '#6b8aed',
          70:  '#89a7ff',
          80:  '#b0c4ff',
          90:  '#d8e2ff',
          95:  '#f0f4ff',
          100: '#ffffff',
        },
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
      },
    },
  },
  plugins: [],
}
