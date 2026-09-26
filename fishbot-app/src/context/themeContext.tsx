import { createContext, useState, useContext } from "react";

type theme = "minimal" | "cutesy";

interface ThemeContextType {
    theme: theme;
    toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType>({
    theme: "minimal",
    toggleTheme: () => {},
});

export function ThemeProvider ({ children }: { children: React.ReactNode}) {
    const [theme, setTheme] = useState<theme>("minimal");

    const toggleTheme = () => {
        setTheme ((prevTheme) => (prevTheme === 'minimal' ? 'cutesy' : 'minimal'));
    };

    return (
        <ThemeContext.Provider value={{ theme, toggleTheme}}>
            {children}
        </ThemeContext.Provider>
    );
}

export const useTheme = () => useContext(ThemeContext);
