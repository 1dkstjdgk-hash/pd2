#include <stdio.h>
void main(){
	int num1,num2,i;
	printf("정수 2개를 입력하시오:");
	scanf("%d %d",&num1,&num2);
	for(i=1;i>=1&&i<=100;i++){
		if(i%num1==0&i%num2==0)
		{printf("1~100까지 정수중 사용자가 입력한 정수의 공배수:%d\n",i);
		}
	}
}
