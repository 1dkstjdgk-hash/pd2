#include <stdio.h>
void triangle(int wid,int hei){
	int i,j;
	for(i=1; i<=hei; i++){
		for(j=1; j<=wid;j++){
			printf("*");
		}
		printf("\n");
	}
}

void main() {
	int width, height;
	printf("가로와 세로 길이를 정수로 입력하시오:");
	scanf("%d %d", &width,&height);
	triangle(width,height);
}
