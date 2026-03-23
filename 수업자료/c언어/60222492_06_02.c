#include <stdio.h>
void main(){
	double h;
	int y;
	printf("당신의 키와 나이를 입력하시오:");
	scanf("%lf %d",&h,&y);
	if(h>=120&&y>=5)
	{printf("승선 가능합니다.\n");
	 printf("좋은시간되세요.");
	}
	else
	{printf("승선 불가능합니다.\n");
	 printf("다음기회에.."); 
	}
}
